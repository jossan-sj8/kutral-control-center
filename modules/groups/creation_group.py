"""Group creation: the four steps of the standard flow.

Details that come from looking at the real directory:

  - **`memberUid` from the start.** The group is born with its members; it is the
    behaviour the inherited flow itself chose after finding that adding them later
    caused trouble.
  - **Case-collision guard.** The directory compares `cn` case-insensitively and
    already has two entries differing only in that: `cn=lab-diez` hanging from the
    root and `cn=Lab-Diez` under `ou=Group`. Creating a third name differing only
    in case would make a search by name return any of them.
  - **Members are validated before creating anything.** If a member does not exist,
    it warns and no half-made group is left behind.

What it does **not** do: it creates no local users on any host, and it does not
change the members' `departmentNumber`. Belonging to a group (`memberUid`) and
having it as the primary group (`gidNumber` + `departmentNumber`) are different
things, and the second one is changed with `users.modification.change_group`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ..common.errors import EntryExists, EntryNotFound, KutralError
from ..common.i18n import t
from ..common.policy import needs_confirmation, should_send_mail
from ..core import config as cfgmod

ACTION_GROUP_CREATE = "create-group"

#: Real group names: letters (upper and lower case), digits, hyphen and
#: underscore. Examples from the directory: `lab-06`, `1000G`, `ma-bioinf`,
#: `lacoro_2025`, `GPRUEBA`. No dots or spaces, because the name is used as a path
#: (`/mnt/beegfs/labs/<group>`) and as a Slurm account.
GROUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{1,30}$")


def validate_group_name(value: Any) -> str:
    """Validate the name of a new group."""
    name = str(value or "").strip()
    if not GROUP_NAME_PATTERN.match(name):
        raise KutralError(t("msg.group.invalid_name", value=value))
    return name


def members_of(entry: Dict[str, Any]) -> List[str]:
    """Members of a group, normalised to a list."""
    members = entry.get("memberUid") or []
    if isinstance(members, str):
        members = [members]
    return [str(member) for member in members]


def _assert_no_case_collision(environment: Any, name: str) -> None:
    """Detect a group that differs only in case.

    `cn` in LDAP is compared case-insensitively, so two groups differing only in that
    are indistinguishable when searching by name. The real directory already has one
    such case, and adding another is not wise.
    """
    for candidate in environment.directory.list_groups():
        existing = str(candidate.get("cn") or "")
        if existing and existing != name and existing.lower() == name.lower():
            raise EntryExists(t("msg.group.case_collision", name=existing))


def _validate_members(environment: Any, members: Sequence[str]) -> List[str]:
    """Check that every member exists, before touching the directory."""
    cleaned: List[str] = []
    for member in members:
        username = str(member or "").strip()
        if not username:
            continue
        if not environment.directory.user_exists(username):
            raise EntryNotFound(t("msg.group.member_missing", member=username))
        if username not in cleaned:
            cleaned.append(username)
    return cleaned


def create_group(environment: Any, name: str, gid: Optional[int] = None,
                 members: Optional[Sequence[str]] = None, is_lab: bool = True,
                 run_hooks: bool = True) -> Dict[str, Any]:
    """Create a whole group: LDAP, SSSD, lab folder and Slurm account."""
    group = validate_group_name(name)
    # Case collision first: if `group_exists` were asked, LDAP (and the fake
    # directory) would find it case-insensitively and the operator would get an
    # "already exists" that does not explain the real problem.
    _assert_no_case_collision(environment, group)
    if environment.directory.group_exists(group):
        raise EntryExists(t("msg.directory.group_exists", group=group))

    members = _validate_members(environment, members or [])
    final_gid = int(gid) if gid is not None else environment.directory.next_gid()
    gid_taken = [g for g in environment.directory.list_groups()
                 if str(g.get("gidNumber")) == str(final_gid)]
    if gid_taken:
        raise EntryExists(t("msg.group.gid_taken", gid=final_gid,
                            group=gid_taken[0].get("cn")))

    movements: List[str] = []
    lab_path = ""
    slurm_accounts: List[str] = []
    hook_results: List[Dict[str, Any]] = []

    if not environment.dry_run:
        # 1. LDAP, with the members from the start
        environment.directory.create_group(group, final_gid, members)
        movements.append(t("msg.move.group_created", gid=final_gid))
        if members:
            movements.append(t("msg.move.members_from_start", count=len(members)))

        # 2. SSSD
        if environment.identity is not None:
            environment.identity.refresh_group(group)
            movements.append(t("msg.move.identity_refreshed"))

        # 3. BeeGFS: lab folder with setgid
        if environment.storage is not None and is_lab:
            lab_path = environment.storage.ensure_lab(group, final_gid)
            movements.append(t("msg.move.lab_folder"))

        # 4. Slurm: account and association of every member
        if environment.slurm is not None and environment.slurm.available:
            if not environment.slurm.account_exists(group):
                environment.slurm.create_account(group)
                movements.append(t("msg.move.slurm_account_new"))
            for member in members:
                environment.slurm.register_user(member, group)
            if members:
                movements.append(t("msg.move.members_associated", count=len(members)))
            slurm_accounts = environment.slurm.associations(members[0]) if members else []

        if run_hooks and environment.hooks is not None:
            hook_results = environment.hooks.run("after_group_create", {
                "group": group, "gid": final_gid, "members": ",".join(members),
                "lab": lab_path or "", "config": environment.config,
            })

    if environment.auditor is not None:
        environment.auditor.record(ACTION_GROUP_CREATE, group, {
            "gid": final_gid, "members": members, "is_lab": is_lab,
            "lab": lab_path, "movements": movements, "hooks": hook_results,
        }, dry_run=environment.dry_run)

    return {"group": group, "gid": final_gid, "members": members, "is_lab": is_lab,
            "lab": lab_path, "slurm_accounts": slurm_accounts,
            "movements": movements, "hooks": hook_results,
            "dn": environment.directory.group_dn(group)}


def describe_group(environment: Any, group: str) -> Dict[str, Any]:
    """Summary of a group: its data, its members, and whether the folder exists."""
    entry = environment.directory.get_group(group)
    if entry is None:
        return {"group": group, "exists": False}
    members = members_of(entry)
    lab_path = ""
    exists = None
    if environment.storage is not None:
        lab_path = environment.storage.lab(group)
        exists = environment.storage.exists(lab_path)
    return {
        "group": group, "exists": True, "dn": environment.directory.group_dn(group),
        "gid": entry.get("gidNumber"), "members": members,
        "member_count": len(members), "lab": lab_path, "lab_exists": exists,
        "slurm_account": (environment.slurm.account_exists(group)
                          if environment.slurm is not None and environment.slurm.available else None),
        "entry": entry,
    }


def render_group(environment: Any, group: str) -> str:
    """Text to show a group on the console."""
    info = describe_group(environment, group)
    if not info.get("exists"):
        return t("msg.group.render.not_found", group=group)
    lines = [
        "=" * 64,
        "  {}: {}".format(t("msg.group.render.title"), info["group"]),
        "=" * 64,
        "  GID             : {}".format(info.get("gid")),
        "  {}   : {}".format(
            t("msg.group.render.members", count=info["member_count"]),
            ", ".join(info["members"]) or t("msg.group.render.none")),
        "  {}  : {} {}".format(
            t("msg.group.render.lab_folder"),
            info.get("lab") or t("msg.group.render.no_folder"),
            "" if info.get("lab_exists") is None else
            (t("msg.group.render.exists") if info.get("lab_exists")
             else t("msg.group.render.not_exists"))),
        "  {} : {}".format(
            t("msg.group.render.slurm_account"),
            t("summary.yes") if info.get("slurm_account") else
            (t("summary.no") if info.get("slurm_account") is False
             else t("msg.group.render.not_checked"))),
        "  DN              : {}".format(info["dn"]),
    ]
    return "\n".join(lines)
