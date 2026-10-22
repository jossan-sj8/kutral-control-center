"""User creation: the whole chain in a single operation.

It replaces the inherited chain, which was:

    tmp1.txt -> create_users.pl -> tmp1.yaml.txt -> add_users.sh
             -> ansible (local users on .154 and .158) -> sacctmgr -> ldapadd
             -> memberUid -> nextcloud -> SSH keys -> msmtp

The steps that **remain** are the ones genuinely needed, in this order:

    1. validate            (before touching anything)
    2. LDAP with a hashed password
    3. the group's memberUid from the start
    4. home in BeeGFS + symlink to the lab
    5. identity refresh (SSSD)
    6. Slurm account with DefaultAccount = the group
    7. configurable hooks (Nextcloud, SSH keys) — the ones that are neither LDAP nor
       Slurm
    8. mail with the credentials
    9. audit

The Ansible steps **are dropped**: creating local users on `.154` and `.158` is the
origin of the two sources of truth that made an LDAP change invisible. SSSD resolves
any directory account with no local copy, so they are not needed — and this is the most
important design decision in the whole project, because it removes the remote `userdel`
and the deletion on two hosts.

Two concrete improvements over the inherited flow:

  - `sn` receives the **surnames**, not the full name (the script wrote the full name
    into `sn`, and that is why 16 accounts in the directory look like that).
  - `gecos` and `displayName` are always filled in, instead of leaving the field empty.
"""

from __future__ import annotations

import datetime
import unicodedata
from typing import Any, Dict, List, Optional

from ..common.errors import EntryExists, EntryNotFound, KutralError
from ..common.i18n import t
from ..common.policy import needs_confirmation, should_send_mail
from ..common.security import generate_secure_password
from ..common.validation import (
    USERNAME_MAX,
    slug,
    split_name,
    suggest_username,
    validate_mail,
    validate_username,
)
from ..core import accounts as accounts_mod
from ..core import config as cfgmod

ACTION_CREATE = "create-user"

#: Required fields of a creation, and the catalog key to show them with.
REQUIRED_FIELDS = {
    "fullname": "field.fullname",
    "username": "field.username",
    "group": "field.group",
    "mail": "field.mail",
}

#: Optional fields, copied into the directory when they are given.
OPTIONAL_FIELDS = {
    "employee_type": "employeeType",
    "institute": "o",
    "course": "description",
}


def _ascii(text: str) -> str:
    """The name stripped of accents, for `gecos`.

    This directory defines `gecos` with **ASCII** syntax, so a name with an accent is
    rejected with `invalidAttributeSyntax` — it happened on 2026-10-20 with the name
    "Cuarta Usuaria": the account was not created, and the request behind
    it (a whole research group) had to wait. The real name, accents included, goes in
    `cn`,
    `displayName` and `sn`, which do accept UTF-8 (the directory already holds
    "Quinto Usuario" in `cn`).

    Anything that is not ASCII after decomposition is dropped, so this can never
    produce another syntax error: worst case the name loses a letter in `gecos`, which
    is the field `ls -l` shows and nothing more.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed
                   if not unicodedata.combining(c) and ord(c) < 128)


def _length(environment: Any) -> int:
    return int(cfgmod.get(environment.config, "cluster.password_length", 12) or 12)


def explicit_permanent_marker(environment: Any) -> bool:
    """Whether an account with no expiry is marked with `-1` or left without the attribute.

    Both forms mean the same to PAM, but **not** to the directory: the 136 active
    accounts carry an explicit `-1`, so a new account without the attribute would look
    like the 17 exceptions. With the explicit marker, all active ones read the same.

    The inherited behaviour can be restored with `cluster.permanent_marker: "ausente"`
    —or `"absent"`, the English name of the same value—, which is what `add_users.sh`
    did.
    """
    value = str(cfgmod.get(environment.config, "cluster.permanent_marker",
                           "explicito")).strip().lower()
    return value not in ("ausente", "absent")


def validate_signup(environment: Any, data: Dict[str, Any]) -> Dict[str, str]:
    """Validate the data of a creation **before** touching the directory.

    A half-done creation is worse than one that does not happen: if the account is
    created and the mail then fails, the person has no credentials and nobody knows.
    """
    cleaned: Dict[str, str] = {}
    for key, label in REQUIRED_FIELDS.items():
        if not str(data.get(key) or "").strip():
            raise KutralError(t("msg.field.missing", field=t(label)))

    cleaned["fullname"] = " ".join(str(data["fullname"]).split())
    cleaned["username"] = validate_username(data["username"])
    cleaned["group"] = str(data["group"]).strip()
    cleaned["mail"] = validate_mail(data["mail"])
    for key, attribute in OPTIONAL_FIELDS.items():
        value = str(data.get(key) or "").strip()
        if value:
            cleaned[key] = value
    if data.get("uid"):
        uid = str(data["uid"]).strip()
        if not uid.isdigit():
            raise KutralError(t("msg.creation.uid_not_number", value=data["uid"]))
        cleaned["uid"] = uid
    return cleaned


def allocate_ids(environment: Any, group_entry: Dict[str, Any],
                 uid: Optional[str] = None) -> Dict[str, int]:
    """Resolve the uidNumber and gidNumber of the creation.

    The uid comes from the maximum in use + 1, which is this cluster's policy. Gaps are
    **not** reused: a freed uid may still own orphan files in BeeGFS, and reassigning it
    would hand them to somebody else.
    """
    uid_number = int(uid) if uid else environment.directory.next_uid()
    gid = group_entry.get("gidNumber")
    if gid is None:
        raise KutralError(t("msg.creation.group_no_gid", group=group_entry.get("cn")))
    return {"uid": uid_number, "gid": int(gid)}


def build_attributes(environment: Any, data: Dict[str, str], ids: Dict[str, int],
                     password: str, expires: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Build the entry's attributes, with the full set the directory uses."""
    given, surname = split_name(data["fullname"])
    username = data["username"]
    base_home = cfgmod.get(environment.config, "paths.beegfs_home", "/mnt/beegfs/home")
    attributes: Dict[str, Any] = {
        "uid": username,
        "cn": data["fullname"],
        "sn": surname,
        "givenName": given,
        "displayName": data["fullname"],
        "gecos": _ascii(data["fullname"]),
        "uidNumber": str(ids["uid"]),
        "gidNumber": str(ids["gid"]),
        "homeDirectory": "{}/{}".format(base_home, username),
        "loginShell": cfgmod.get(environment.config, "cluster.default_shell", "/bin/bash"),
        "mail": data["mail"],
        "departmentNumber": data["group"],
        # The password travels in the clear **towards the adapter**, which is the one
        # that hashes it with the cluster's scheme. That way the hash is never computed
        # twice nor stored in the clear anywhere in between.
        "userPassword": password,
        "shadowLastChange": str(accounts_mod.date_to_shadow_expire(datetime.date.today())),
    }
    if data.get("employee_type"):
        attributes["employeeType"] = data["employee_type"]
    if data.get("institute"):
        attributes["o"] = data["institute"]
    if data.get("course"):
        attributes["description"] = data["course"]
    if expires is not None:
        attributes["shadowExpire"] = str(accounts_mod.date_to_shadow_expire(expires))
    elif explicit_permanent_marker(environment):
        # Account with no expiry, marked like the 136 active ones in the directory.
        attributes["shadowExpire"] = str(cfgmod.get(
            environment.config, "cluster.shadow_expire_permanent", -1))
    return attributes


def create_user(environment: Any, data: Dict[str, Any], password: Optional[str] = None,
                send_mail: Optional[bool] = None, run_hooks: bool = True,
                expires: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Create a whole account. It returns the password so it can be shown.

    The group **must exist**: if not, it warns with a clear error instead of creating a
    half-made group. `groups.creation_group.create_group` is there for that.
    """
    data = validate_signup(environment, data)
    group_entry = environment.directory.get_group(data["group"])
    if group_entry is None:
        raise EntryNotFound(t("msg.creation.group_missing", group=data["group"]))
    if environment.directory.user_exists(data["username"]):
        raise EntryExists(t("msg.account.exists", username=data["username"]))

    ids = allocate_ids(environment, group_entry, data.get("uid"))
    new_password = password or generate_secure_password(_length(environment))
    attributes = build_attributes(environment, data, ids, new_password, expires)
    home = attributes["homeDirectory"]
    username = data["username"]

    movements: List[str] = []
    hook_results: List[Dict[str, Any]] = []

    if not environment.dry_run:
        environment.directory.create_user(attributes)
        movements.append(t("msg.move.ldap_created"))
        if environment.directory.add_member(data["group"], username):
            movements.append(t("msg.move.member_added", group=data["group"]))
        if environment.storage is not None:
            environment.storage.ensure_home(username, ids["uid"], ids["gid"])
            environment.storage.ensure_group_link(username, data["group"],
                                                  ids["uid"], ids["gid"])
            # The bash history folder carries the user's name, not their uid: recreating
            # a deleted account leaves it owned by the old user and the login fails with
            # "Permission denied". It is created or fixed here.
            environment.storage.ensure_history(username, ids["uid"], ids["gid"])
            movements.append(t("msg.move.home_created"))
        if environment.identity is not None:
            environment.identity.refresh_all()
        if environment.slurm is not None and environment.slurm.available:
            if not environment.slurm.account_exists(data["group"]):
                environment.slurm.create_account(data["group"])
                movements.append(t("msg.move.slurm_account_created",
                                   group=data["group"]))
            environment.slurm.register_user(username, data["group"])
            movements.append(t("msg.move.slurm_associated", group=data["group"]))
        if run_hooks and environment.hooks is not None:
            hook_results = environment.hooks.run("after_create", {
                "username": username, "uid": ids["uid"], "gid": ids["gid"],
                "group": data["group"], "mail": data["mail"], "home": home,
                "password": new_password, "config": environment.config,
            })

    sent = False
    if (environment.mailer is not None and not environment.dry_run
            and should_send_mail(environment, send_mail)):
        sent = environment.mailer.send("welcome", data["mail"], username=username,
                                       temp_pass=new_password, group=data["group"],
                                       full_name=data["fullname"])

    if environment.auditor is not None:
        environment.auditor.record(ACTION_CREATE, username, {
            "uid": ids["uid"], "gid": ids["gid"], "group": data["group"],
            "mail": data["mail"], "movements": movements, "hooks": hook_results,
            "mail_sent": sent, "password": new_password,
        }, dry_run=environment.dry_run)

    # A failing hook cannot stay silent: the space in Nextcloud, or whatever it does,
    # either got done or did not, and the operator has to know. It used to show up only
    # in `--json` and in the audit log.
    warnings = [t("msg.creation.hook_failed", command=hook_result.get("command"),
                  error=(hook_result.get("error") or hook_result.get("stderr")
                         or t("msg.creation.hook_no_detail")))
                for hook_result in hook_results if not hook_result.get("ok")]

    return {
        "username": username, "uid": ids["uid"], "gid": ids["gid"],
        "group": data["group"], "mail": data["mail"], "home": home,
        "password": new_password, "expires": expires, "movements": movements,
        "hooks": hook_results, "warnings": [warnings] if warnings else [],
        "mail_sent": sent,
        "pending_confirmation": needs_confirmation(environment, send_mail),
        "dn": environment.directory.user_dn(username),
    }


def suggest_username_from(fullname: str, environment: Any) -> str:
    """Propose a free username, taking into account the ones that already exist."""
    taken = [str(user.get("uid")) for user in environment.directory.list_users()]
    return suggest_username(fullname, taken=taken)


def username_from_mail(mail: str) -> str:
    """Extract a candidate username from a mail address. Only as a suggestion."""
    return slug(str(mail or "").split("@")[0])[:USERNAME_MAX].replace(" ", "")
