"""Group modification: adding and removing members.

It is what `add_group.sh` does (`ldapmodify` with `add: memberUid`) and, on the other
side, what **never existed** in the inherited flow: removing somebody from a group.

Two things the inherited code did not do and this one does:

  - `memberUid` is added with MODIFY_ADD and removed with MODIFY_DELETE. With a
    `replace`, **every** other member of the group would be wiped.
  - When adding or removing, the affected person's Slurm account is re-associated,
    because on this cluster the account **is** the group: being a member in LDAP and
    outside Slurm (or the other way round) is a half membership.

Out of scope, deliberately: **renaming a group** (changing the `cn` would force moving
the lab folder, the Slurm account and every member's `departmentNumber`: it is a new
creation plus a migration) and **changing the gid** (it would leave existing files with
the old gid).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..common.i18n import t
from ..common.policy import needs_confirmation, should_send_mail
from ..users.modification import primary_group

ACTION_GROUP_MEMBERSHIP = "group-membership"


def _require_group(environment: Any, group: str) -> Dict[str, Any]:
    from ..common.errors import EntryNotFound

    entry = environment.directory.get_group(group)
    if entry is None:
        raise EntryNotFound(t("msg.group.not_found", group=group))
    return entry


def _mail(environment: Any, username: str, group: str, send_mail: Optional[bool]) -> bool:
    """Notify the person by mail, reusing the modification template."""
    if environment.mailer is None or environment.dry_run:
        return False
    if not should_send_mail(environment, send_mail):
        return False
    entry = environment.directory.get_user(username) or {}
    if not entry.get("mail"):
        return False
    return environment.mailer.send("modification", entry["mail"], username=username,
                                   changes=[(t("msg.change.secondary_groups"), "", group)])


def add_members(environment: Any, group: str, usernames: Sequence[str],
                send_mail: Optional[bool] = None) -> Dict[str, Any]:
    """Add members to a group, in LDAP and in Slurm."""
    entry = _require_group(environment, group)
    from .creation_group import members_of

    before = set(members_of(entry))
    added: List[str] = []
    already: List[str] = []
    missing: List[str] = []

    for username in usernames:
        name = str(username or "").strip()
        if not name:
            continue
        if not environment.directory.user_exists(name):
            missing.append(name)
            continue
        if name in before:
            already.append(name)
            continue
        if not environment.dry_run:
            environment.directory.add_member(group, name)
            if environment.slurm is not None and environment.slurm.available:
                environment.slurm.register_user(name, group)
        added.append(name)

    if added and not environment.dry_run and environment.identity is not None:
        environment.identity.refresh_group(group)

    sent = []
    for name in added:
        if _mail(environment, name, group, send_mail):
            sent.append(name)

    if environment.auditor is not None:
        environment.auditor.record(ACTION_GROUP_MEMBERSHIP, group, {
            "action": "add", "added": added, "already": already,
            "missing": missing, "mail": sent,
        }, dry_run=environment.dry_run)

    return {"group": group, "added": added, "already": already,
            "missing": missing, "mail_sent": sent,
            "pending_confirmation": needs_confirmation(environment, send_mail)}


def remove_members(environment: Any, group: str, usernames: Sequence[str],
                   drop_slurm: bool = False) -> Dict[str, Any]:
    """Remove members from a group.

    `drop_slurm` is off by default: removing somebody from the Slurm account may
    affect running jobs, so it is done only when asked for.

    Users whose **primary group** is this one are skipped and reported separately:
    removing their `memberUid` would not change their `gidNumber` and would leave them
    in an incoherent state. `change_group` is there for that.
    """
    entry = _require_group(environment, group)
    from .creation_group import members_of

    before = set(members_of(entry))
    removed: List[str] = []
    not_members: List[str] = []
    skipped_primary: List[str] = []

    for username in usernames:
        name = str(username or "").strip()
        if not name:
            continue
        if name not in before:
            not_members.append(name)
            continue
        user = environment.directory.get_user(name) or {}
        if primary_group(environment, user) == group:
            skipped_primary.append(name)
            continue
        if not environment.dry_run:
            environment.directory.remove_member(group, name)
            if drop_slurm and environment.slurm is not None and environment.slurm.available:
                # Only the association with THIS account is removed; the rest are kept.
                remaining = [account for account in environment.slurm.associations(name)
                             if account != group]
                environment.slurm.remove_user(name)
                for account in remaining:
                    environment.slurm.register_user(name, account)
        removed.append(name)

    if removed and not environment.dry_run and environment.identity is not None:
        environment.identity.refresh_group(group)

    if environment.auditor is not None:
        environment.auditor.record(ACTION_GROUP_MEMBERSHIP, group, {
            "action": "remove", "removed": removed, "not_members": not_members,
            "skipped_primary": skipped_primary, "drop_slurm": drop_slurm,
        }, dry_run=environment.dry_run)

    return {"group": group, "removed": removed, "not_members": not_members,
            "skipped_primary": skipped_primary, "slurm_dropped": bool(drop_slurm)}
