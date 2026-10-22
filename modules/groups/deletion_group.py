"""Group deletion, with the guards the inherited flow did not have.

A group on this cluster is not just an LDAP entry: it is a lab folder with data
belonging to several people, a Slurm account with possibly running jobs, and the
`gidNumber` of every member. Deleting it without looking is the most destructive
operation in the control center, so it refuses unless explicitly asked, and it always
says **why** it refuses and who is affected.

Three deliberate refusals:

  1. **It has members** -> they are listed. A group with people is not deleted: it is
     emptied.
  2. **It is somebody's primary group** (`gidNumber` or `departmentNumber`) -> those
     accounts would be left pointing at a group that does not exist.
  3. **The lab folder is kept** unless `remove_lab_dir=True`, because it may hold data
     that belongs to its members and not to the group.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.errors import EntryNotFound, KutralError
from ..common.i18n import t
from ..users.modification import primary_group

ACTION_GROUP_DELETE = "delete-group"


def users_linked_to(environment: Any, group: str, entry: Dict[str, Any]) -> List[str]:
    """Users whose **primary group** is this one.

    It is checked in two ways because in the directory the primary group is expressed
    in two manners: `gidNumber` (numeric) and `departmentNumber` (the name).
    """
    gid = str(entry.get("gidNumber"))
    linked = []
    for user in environment.directory.list_users():
        if primary_group(environment, user) == group:
            linked.append(str(user.get("uid")))
        elif str(user.get("gidNumber")) == gid:
            linked.append(str(user.get("uid")))
    return sorted(set(linked))


def delete_group(environment: Any, group: str, force: bool = False,
                 remove_lab_dir: bool = False, drop_slurm: bool = True) -> Dict[str, Any]:
    """Delete a group. It refuses if it has members or is somebody's primary one."""
    entry = environment.directory.get_group(group)
    if entry is None:
        raise EntryNotFound(t("msg.group.not_found", group=group))

    from .creation_group import members_of

    members = members_of(entry)
    linked = users_linked_to(environment, group, entry)

    if members and not force:
        raise KutralError(t("msg.group.has_members", group=group, count=len(members),
                            members=", ".join(members[:8])
                            + ("…" if len(members) > 8 else "")))
    if linked and not force:
        raise KutralError(t("msg.group.is_primary", group=group, count=len(linked),
                            users=", ".join(linked[:8])
                            + ("…" if len(linked) > 8 else "")))

    lab = ""
    lab_removed = False
    if environment.storage is not None:
        lab = environment.storage.lab(group)

    if not environment.dry_run:
        # 1. LDAP. It is deleted by DN and not by name: the port exposes `delete`, and
        # that way exactly the entry read and validated above is deleted.
        environment.directory.delete(entry["dn"])
        # 2. identity
        if environment.identity is not None:
            environment.identity.refresh_group(group)
        # 3. Slurm, **only if the account exists**: a group can be in the directory and
        # not be a Slurm account (`gprueba2/3/4` and `GPRUEBA` are like that). Without
        # this check, `sacctmgr` fails *after* the LDAP entry has been deleted and the
        # deletion is left half done, with an error on screen.
        account_dropped = False
        if drop_slurm and environment.slurm is not None and environment.slurm.available:
            if environment.slurm.account_exists(group):
                account_dropped = environment.slurm.delete_account(group)
        # 4. folder, only if it was asked for
        if remove_lab_dir and environment.storage is not None and lab:
            environment.storage.remove_home(lab)   # same mechanism: deleting a tree
            lab_removed = True
    else:
        account_dropped = False

    if environment.auditor is not None:
        environment.auditor.record(ACTION_GROUP_DELETE, group, {
            "members_at_delete": members, "primary_of": linked,
            "force": force, "slurm_account_removed": bool(account_dropped),
            "lab": lab, "lab_removed": lab_removed,
        }, dry_run=environment.dry_run)

    return {"group": group, "deleted": True, "members_at_delete": members,
            "primary_of": linked, "slurm_account_removed": bool(account_dropped),
            "lab": lab, "lab_removed": lab_removed, "force": force,
            "lab_warning": (None if lab_removed or not lab else
                            t("msg.group.lab_kept", path=lab))}
