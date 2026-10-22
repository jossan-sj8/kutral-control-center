"""Final deletion of an account, with a check afterwards.

It is the most destructive operation in the control center, and the one that touches
the most things:

    1. rollback LDIF (the last chance to look before)
    2. remove it from the `memberUid` of every group (otherwise memberships are left
       pointing at a user that no longer exists)
    3. delete the LDAP entry
    4. remove its Slurm associations, backing them up first
    5. decide what happens to the home: keep, archive or delete
    6. refresh identity
    7. **check that the person disappeared from the system**

Step 7 is the direct answer to what used to happen by hand: *"if I did not delete it
from 154 and 158, it was not deleted"*. The cause is that `nsswitch` resolves `files`
before `sss`, so a copy in `/etc/passwd` keeps the user alive even though its LDAP entry
is gone. Instead of a blind remote `userdel` over SSH, here it is **checked**, and it
reports which host holds the old copy, with the exact command to clean it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.errors import EntryNotFound
from ..common.i18n import t
from ..core import config as cfgmod

ACTION_DELETE = "delete-user"

#: What to do with the home directory.
HOME_KEEP = "keep"
HOME_ARCHIVE = "archive"
HOME_REMOVE = "remove"


def delete_user(environment: Any, username: str, home_action: str = HOME_KEEP,
                remove_slurm: bool = True) -> Dict[str, Any]:
    """Delete the account. It also returns the result of the check."""
    entry = environment.directory.get_user(username)
    if entry is None:
        raise EntryNotFound(t("msg.user.not_found", username=username))
    if home_action not in (HOME_KEEP, HOME_ARCHIVE, HOME_REMOVE):
        raise ValueError(t("msg.home_action.invalid", value=home_action))

    groups = environment.directory.memberships(username)
    if environment.dry_run:
        return {"username": username, "deleted": False, "dry_run": True,
                "groups": groups, "home_action": home_action,
                "message": t("msg.delete.simulated", username=username,
                             groups=len(groups))}

    # The uid is never reused: the bash history folder and the orphan files in BeeGFS
    # carry the number, not the name.
    environment.directory.retire_uid(entry.get("uidNumber"), username)
    # `for_restore=True`: this LDIF has to be able to recreate the deleted account, not
    # merely revert a change. It is the only safety net of the deletion.
    backup = environment.directory.save_entry(environment.directory.user_dn(username),
                                              for_restore=True)
    for group in groups:
        environment.directory.remove_member(group, username)

    environment.directory.delete(environment.directory.user_dn(username))

    slurm_accounts: List[str] = []
    if remove_slurm and environment.slurm is not None and environment.slurm.available:
        slurm_accounts = environment.slurm.associations(username)
        if slurm_accounts:
            environment.slurm.save_associations(username)
            environment.slurm.remove_user(username)

    home = str(entry.get("homeDirectory") or "")
    home_result: Optional[str] = None
    if environment.storage is not None and home:
        if home_action == HOME_ARCHIVE:
            home_result = environment.storage.archive_home(username, home)
            environment.storage.remove_home(home)
        elif home_action == HOME_REMOVE:
            environment.storage.remove_home(home)
            home_result = t("msg.delete.home_removed")

    if environment.identity is not None:
        environment.identity.refresh_all()

    verification = verify_identity_gone(environment, username)

    if environment.auditor is not None:
        environment.auditor.record(ACTION_DELETE, username, {
            "groups": groups, "slurm_accounts": slurm_accounts, "backup": backup,
            "home_action": home_action, "home": home, "home_result": home_result,
            "identity": verification,
        })

    return {"username": username, "deleted": True, "groups": groups,
            "slurm_accounts": slurm_accounts, "backup": backup,
            "home_action": home_action, "home_result": home_result,
            "identity": verification,
            "message": t("msg.delete.done", username=username)}


def verify_identity_gone(environment: Any, username: str) -> Dict[str, Any]:
    """Check whether the person really disappeared from the system.

    If it still resolves, it is because a **local** account exists on this host: the
    copy in `/etc/passwd` wins over LDAP. The warning and the command to clean it are
    returned, instead of leaving the operator wondering.
    """
    result: Dict[str, Any] = {"resolved": False, "local_account": None,
                              "host": None, "hint": None}
    if environment.identity is None:
        return result

    try:
        import socket
        result["host"] = socket.gethostname()
    except Exception:  # pragma: no cover
        pass

    resolution = environment.identity.resolve(username)
    if resolution is None:
        return result

    result["resolved"] = True
    result["source"] = (resolution.get("source")
                        if isinstance(resolution, dict) else None)
    if environment.identity.local_account_exists(username):
        result["local_account"] = True
        result["hint"] = t("msg.delete.local_hint", username=username,
                           host=result["host"] or t("msg.host.this"))
    else:
        result["hint"] = t("msg.delete.still_resolved")
    return result


def purge_local_account_hint(environment: Any, username: str) -> Optional[str]:
    """Return only the help text, or None if there is nothing to clean."""
    return verify_identity_gone(environment, username).get("hint")


def home_action_for(args: Any) -> str:
    """Translate the CLI flags into the action taken on the home.

    By default it is **kept**: deleting a person's data is irreversible, and disk is the
    only cheap thing on the cluster. Deleting it requires asking for it explicitly.
    """
    if getattr(args, "archive_home", False):
        return HOME_ARCHIVE
    if getattr(args, "delete_home", False):
        return HOME_REMOVE
    return HOME_KEEP


def default_archive_path(environment: Any, username: str) -> str:
    base = cfgmod.get(environment.config, "paths.beegfs_home", "/mnt/beegfs/home")
    return "{}/deleted_archives/{}.tar.gz".format(base, username)
