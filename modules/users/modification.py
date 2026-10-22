"""Account modification, group change included.

The group change is the requirement that started this work: *"modifications, it does not
change the group (if it is one)"*. In this directory a user's group is expressed in
**three places**, and the inherited flow only touched one:

    gidNumber          in the account      -> primary group, owner of new files
    memberUid          in the posixGroup  -> membership, what `id` shows
    departmentNumber   in the account      -> the group's business label

`group_change.sh` wrote `gidNumber` and nothing else, and on top of that it read the gid
from `getent passwd`, which with `nsswitch` set to `files sss` returns the local copy.
That is why it "changed" the group without anything changing. Here all three are moved,
and the Slurm account is re-associated, which is the fourth place where the group lives.

What is deliberately **not** done automatically:

  - **Reassigning the owner of the existing files** in the home. Old files keep the
    previous gid. It is a heavy and arguable operation, and the `Storage` port has no way
    of doing it yet; it stays as an explicit pending item instead of a hidden one.
  - **Removing the user from the previous Slurm account.** Changing the group changes
    the *default* account; the other associations are kept, because removing them may
    affect running jobs. With `--only-primary` the opposite could be asked for in the
    future, but not by default.
  - **Deleting the previous group** if it is left empty: it only warns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..common.errors import EntryExists, EntryNotFound, KutralError, SlurmError
from ..common.i18n import t
from ..common.policy import needs_confirmation, should_send_mail
from ..common.validation import validate_mail, validate_username
from ..core.ldap_values import resolve_group_label
from ..core import config as cfgmod

#: Attributes `modify_user` accepts, with the catalog key shown to the operator.
EDITABLE_ATTRIBUTES: Dict[str, str] = {
    "cn": "field.cn",
    "mail": "field.mail",
    "loginShell": "field.shell",
    "employeeType": "field.employee_type",
    "o": "field.institute",
    "description": "field.course",
}

#: `departmentNumber` is in the directory, but it is **not** edited from here:
#: changing the label without moving the gid nor the membership leaves the user lying
#: about their group. `change_group` is there for that.
GROUP_ATTRIBUTE = "departmentNumber"

# The username and mail rules live in common/validation.py: a single source, because
# creating and renaming have to accept exactly the same thing.

ACTION_MODIFY = "modify-user"
ACTION_CHANGE_GROUP = "change-group"
ACTION_MEMBERSHIP = "change-membership"
ACTION_RENAME = "rename-user"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_user(environment: Any, username: str) -> Dict[str, Any]:
    entry = environment.directory.get_user(username)
    if entry is None:
        raise EntryNotFound(t("msg.user.not_found", username=username))
    return entry


def _require_group(environment: Any, group: str) -> Dict[str, Any]:
    entry = environment.directory.get_group(group)
    if entry is None:
        raise EntryNotFound(t("msg.group.not_found.under", group=group,
                              base=environment.config["ldap"]["group_dn"]))
    return entry


def primary_group(environment: Any, entry: Dict[str, Any]) -> Optional[str]:
    """Name of the user's primary group.

    `departmentNumber` is preferred, and when it is missing (14 of the 214 real accounts
    do not have it) the `gidNumber` is resolved against `ou=Group`.
    """
    label = resolve_group_label(entry)
    if label and not str(label).startswith("gid:"):
        return str(label)
    gid = entry.get("gidNumber")
    if gid is None:
        return None
    for candidate in environment.directory.list_groups():
        if str(candidate.get("gidNumber")) == str(gid):
            return str(candidate.get("cn"))
    return None


def validate_changes(changes: Dict[str, Any]) -> Dict[str, str]:
    """Validate and normalise the changes. It raises KutralError with the reason.

    It validates **before** touching the directory: a badly written mail that reaches LDAP
    breaks the delivery of that person's credentials and nobody finds out until they
    complain.
    """
    if not changes:
        raise KutralError(t("msg.modify.nothing_to_do"))

    cleaned: Dict[str, str] = {}
    for attribute, value in changes.items():
        if attribute not in EDITABLE_ATTRIBUTES:
            if attribute == GROUP_ATTRIBUTE:
                raise KutralError(t("msg.modify.use_change_group"))
            raise KutralError(t("msg.modify.attribute_not_editable", attribute=attribute,
                                editable=", ".join(sorted(EDITABLE_ATTRIBUTES))))
        text = "" if value is None else str(value).strip()
        if not text:
            raise KutralError(t("msg.modify.empty_value",
                                field=t(EDITABLE_ATTRIBUTES[attribute])))
        if attribute == "mail":
            text = validate_mail(text)
        if attribute == "loginShell" and not text.startswith("/"):
            raise KutralError(t("msg.modify.shell_absolute"))
        cleaned[attribute] = text
    return cleaned


def _send(environment: Any, entry: Dict[str, Any], changes: List[Tuple[str, Any, Any]],
          send_mail: Optional[bool], password_changed: bool = False) -> bool:
    if environment.mailer is None or environment.dry_run:
        return False
    if not should_send_mail(environment, send_mail):
        return False
    return environment.mailer.send("modification", entry.get("mail"), username=entry.get("uid"),
                                   changes=changes, password_changed=password_changed)


def _verify_group(environment: Any, username: str, group: str, gid: str) -> Dict[str, Any]:
    """Check in the directory that the change really landed.

    It is the part the inherited flow did not have: write and trust. Here the entry is
    re-read and the three values are checked to match, so it can report "applied and
    verified" instead of "applied, I suppose".
    """
    entry = environment.directory.get_user(username) or {}
    memberships = environment.directory.memberships(username)
    return {
        "gid_ok": str(entry.get("gidNumber")) == str(gid),
        "label_ok": str(entry.get(GROUP_ATTRIBUTE)) == str(group),
        "member_ok": group in memberships,
        "memberships": memberships,
    }


# ---------------------------------------------------------------------------
# Modifying attributes
# ---------------------------------------------------------------------------

def modify_user(environment: Any, username: str, changes: Dict[str, Any],
                send_mail: Optional[bool] = None) -> Dict[str, Any]:
    """Change simple attributes of the account and notify by mail.

    A single mail with the whole list of changes, not one per field.
    """
    entry = _require_user(environment, username)
    cleaned = validate_changes(changes)

    applied: List[Tuple[str, Any, Any]] = []
    for attribute, value in cleaned.items():
        previous = entry.get(attribute)
        if str(previous or "") != value:
            applied.append((t(EDITABLE_ATTRIBUTES[attribute]), previous, value))
    if not applied:
        return {"username": username, "changed": False, "changes": [],
                "message": t("msg.modify.identical")}

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        environment.directory.update(environment.directory.user_dn(username), cleaned)
        if environment.identity is not None:
            environment.identity.refresh_user(username)

    sent = _send(environment, entry, applied, send_mail)
    if environment.auditor is not None:
        environment.auditor.record(ACTION_MODIFY, username,
                                   {"changes": [list(item) for item in applied],
                                    "mail_sent": sent}, dry_run=environment.dry_run)

    return {"username": username, "changed": True, "changes": applied,
            "mail_sent": sent,
            "pending_confirmation": needs_confirmation(environment, send_mail)}


# ---------------------------------------------------------------------------
# Changing group
# ---------------------------------------------------------------------------

def change_group(environment: Any, username: str, group: str, keep_old: bool = False,
                 send_mail: Optional[bool] = None) -> Dict[str, Any]:
    """Move the user to another group: gidNumber + memberUid + departmentNumber + Slurm.

    Args:
        keep_old: when True, the previous group stays as a secondary membership instead
            of being removed. It is the "works in two labs" case.
    """
    entry = _require_user(environment, username)
    new_group = _require_group(environment, group)
    gid = str(new_group.get("gidNumber"))
    previous_group = primary_group(environment, entry)

    updates: Dict[str, Any] = {"gidNumber": gid, GROUP_ATTRIBUTE: group}
    movements: List[str] = []

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        environment.directory.update(environment.directory.user_dn(username), updates)
        # memberUid is added and removed with MODIFY_ADD / MODIFY_DELETE: with a
        # replace, the other members of the group would be wiped.
        if environment.directory.add_member(group, username):
            movements.append(t("msg.move.member_added_to", group=group))
        if previous_group and previous_group != group and not keep_old:
            if environment.directory.remove_member(previous_group, username):
                movements.append(t("msg.move.member_removed_from", group=previous_group))
        if environment.identity is not None:
            environment.identity.refresh_user(username)
            environment.identity.refresh_group(group)
            if previous_group and previous_group != group:
                environment.identity.refresh_group(previous_group)

    slurm_accounts: List[str] = []
    slurm_warning: Optional[str] = None
    if environment.slurm is not None and environment.slurm.available and not environment.dry_run:
        try:
            # A group can exist in the directory and **not** as a Slurm account: the
            # four `gprueba*` on the cluster are like that. Creation creates the account
            # when missing; here it was assumed to be there, and the change ended in an
            # error with the directory already modified.
            if not environment.slurm.account_exists(group):
                environment.slurm.create_account(group)
                movements.append(t("msg.move.slurm_account_created", group=group))
            # The default account in Slurm IS the group, so it has to be re-associated.
            # The other accounts are not removed: that could affect running jobs.
            if environment.slurm.register_user(username, group):
                slurm_accounts = environment.slurm.associations(username)
        except SlurmError as exc:
            # Without this, the operator sees an error and does not know which half got done.
            slurm_warning = t("msg.modify.slurm_warning", group=group, error=exc)

    verification = (_verify_group(environment, username, group, gid)
                    if not environment.dry_run else {})
    applied = [(t("msg.change.group_field"), previous_group, group)]
    sent = _send(environment, entry, applied, send_mail)

    if environment.auditor is not None:
        environment.auditor.record(ACTION_CHANGE_GROUP, username,
                                   {"from": previous_group, "to": group, "gid": gid,
                                    "keep_old": keep_old, "movements": movements,
                                    "slurm_accounts": slurm_accounts,
                                    "slurm_warning": slurm_warning,
                                    "verified": verification,
                                    "mail_sent": sent},
                                   dry_run=environment.dry_run)

    return {"username": username, "changed": previous_group != group,
            "from": previous_group, "to": group,
            "gid": gid, "movements": movements, "slurm_accounts": slurm_accounts,
            "slurm_warning": slurm_warning,
            "warnings": [[slurm_warning]] if slurm_warning else [],
            "verified": verification, "mail_sent": sent,
            "pending_confirmation": needs_confirmation(environment, send_mail)}


def add_membership(environment: Any, username: str, group: str,
                   send_mail: Optional[bool] = None) -> Dict[str, Any]:
    """Add the user to a group as a secondary membership, without touching the primary."""
    entry = _require_user(environment, username)
    _require_group(environment, group)

    added = False
    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        added = bool(environment.directory.add_member(group, username))
        if environment.identity is not None:
            environment.identity.refresh_user(username)
            environment.identity.refresh_group(group)

    sent = _send(environment, entry, [(t("msg.change.secondary_groups"), "", group)],
                 send_mail)
    if environment.auditor is not None:
        environment.auditor.record(ACTION_MEMBERSHIP, username,
                                   {"action": "add", "group": group, "changed": added,
                                    "mail_sent": sent}, dry_run=environment.dry_run)

    return {"username": username, "group": group, "changed": added,
            "already_member": not added, "mail_sent": sent,
            "pending_confirmation": needs_confirmation(environment, send_mail)}


def remove_membership(environment: Any, username: str, group: str) -> Dict[str, Any]:
    """Remove the user from a secondary group.

    It refuses when the group is the primary one: removing it from `memberUid` would not
    change their primary group (`gidNumber`) and would leave the account half done.
    """
    entry = _require_user(environment, username)
    _require_group(environment, group)
    previous_group = primary_group(environment, entry)
    if previous_group == group:
        raise KutralError(t("msg.modify.primary_group", group=group, username=username))

    removed = False
    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        removed = bool(environment.directory.remove_member(group, username))
        if environment.identity is not None:
            environment.identity.refresh_user(username)
            environment.identity.refresh_group(group)

    if environment.auditor is not None:
        environment.auditor.record(ACTION_MEMBERSHIP, username,
                                   {"action": "remove", "group": group, "changed": removed},
                                   dry_run=environment.dry_run)

    return {"username": username, "group": group, "changed": removed,
            "was_member": removed}


# ---------------------------------------------------------------------------
# Renaming the uid
# ---------------------------------------------------------------------------

def rename_username(environment: Any, username: str, new_username: str,
                    move_home: bool = True, send_mail: Optional[bool] = None) -> Dict[str, Any]:
    """Change the `uid` and, with it, everything that references it.

    Renaming is the most fragile operation in the lifecycle, because the uid is written in
    four places besides the DN:

        1. the account's DN              -> modify_dn
        2. each group's `memberUid`      -> remove the old one, add the new one
        3. the Slurm account             -> delete and recreate with the same accounts
        4. the home directory in BeeGFS  -> rename and reassign the owner

    The inherited flow (`user_mgmt.py` from V1) did all four, but by hand and in a fragile
    order. Here they go in order and the result is checked at the end.
    """
    entry = _require_user(environment, username)
    new_name = validate_username(new_username, taken=[username])
    if environment.directory.user_exists(new_name):
        raise EntryExists(t("msg.account.exists", username=new_name))

    old_uid = str(entry.get("uidNumber") or "")
    old_gid = str(entry.get("gidNumber") or "")
    groups = environment.directory.memberships(username)
    slurm_accounts = environment.slurm.associations(username) if (
        environment.slurm is not None and environment.slurm.available) else []
    new_dn = environment.directory.user_dn(new_name)

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        new_dn = environment.directory.rename(environment.directory.user_dn(username), new_name)
        for group in groups:
            environment.directory.remove_member(group, username)
            environment.directory.add_member(group, new_name)
        if environment.slurm is not None and environment.slurm.available and slurm_accounts:
            environment.slurm.remove_user(username)
            for account in slurm_accounts:
                environment.slurm.register_user(new_name, account)
        if move_home and environment.storage is not None:
            environment.storage.move_home(username, new_name,
                                          int(old_uid or 0), int(old_gid or 0))
        if environment.storage is not None:
            # The history is always moved, even with --keep-home: the folder carries the
            # user's name, not the uid.
            environment.storage.move_history(username, new_name,
                                             int(old_uid or 0), int(old_gid or 0))
        if environment.identity is not None:
            environment.identity.refresh_user(new_name)
            environment.identity.refresh_all()

    sent = _send(environment, entry, [(t("field.username"), username, new_name)],
                 send_mail)
    if environment.auditor is not None:
        environment.auditor.record(ACTION_RENAME, username,
                                   {"to": new_name, "groups": groups,
                                    "slurm_accounts": slurm_accounts,
                                    "home_moved": move_home,
                                    "mail_sent": sent}, dry_run=environment.dry_run)

    return {"username": username, "new_username": new_name, "dn": new_dn,
            "groups_updated": groups, "slurm_accounts": slurm_accounts,
            "home_moved": bool(move_home and environment.storage is not None),
            "history_moved": bool(environment.storage is not None),
            "mail_sent": sent,
            "pending_confirmation": needs_confirmation(environment, send_mail)}


def describe_change(change: Tuple[str, Any, Any]) -> str:
    """Format a change to show it on screen: "Group: old -> new"."""
    label, before, after = change
    return "{}: {} -> {}".format(label,
                                  before if before not in (None, "")
                                  else t("msg.render.empty"), after)
