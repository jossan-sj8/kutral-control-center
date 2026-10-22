"""Account lifecycle: deactivate, reactivate and reset the password.

It is what four loose scripts do today (`deactivate_user.sh`, `activate_user.sh`,
plus a hand-run `ldappasswd` and cleaning the local accounts on `.154` and `.158`), and
it fixes three problems:

1. **`deactivate_user.sh` generated the LDIF and never applied it**: they were two
   manual steps, easy to leave half done. Here it is applied and verified.
2. **`activate_user.sh` computed the expiry date and never wrote it.** That is why
   there are 7 accounts with `shadowExpire=20819` set by hand. Here the date is really
   applied, with `--expires`.
3. **Neither of them touched Slurm.** Reactivating the LDAP account while leaving the
   user with no Slurm account is a half reactivation. Here it is re-associated, and the
   previous associations **are backed up before** being removed, so that a user of two
   labs does not lose the second one.

Every step is recorded in the audit log, and a rollback LDIF is written before touching
the entry.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from ..common.errors import SlurmError
from ..common.i18n import t
from ..common.policy import needs_confirmation, should_send_mail
from ..common.security import generate_secure_password
from ..core import accounts as accounts_mod
from ..core import config as cfgmod
from ..core.ldap_values import resolve_group_label

#: Audit actions, in a single place so the log stays comparable.
ACTION_DEACTIVATE = "deactivate-user"
ACTION_REACTIVATE = "reactivate-user"
ACTION_RESET_PASSWORD = "reset-password"
ACTION_EXPIRE_SET = "expire-set"


def _password_length(environment: Any) -> int:
    return int(cfgmod.get(environment.config, "cluster.password_length", 12) or 12)


def _nologin_shell(environment: Any) -> str:
    return cfgmod.get(environment.config, "cluster.nologin_shell", "/sbin/nologin")


def _default_shell(environment: Any) -> str:
    return cfgmod.get(environment.config, "cluster.default_shell", "/bin/bash")


def _fallback_account(environment: Any, entry: Dict[str, Any]) -> str:
    """Slurm account to re-associate with when there is no backup.

    On this cluster the account **is the user's group** (`sacctmgr create user name=X
    DefaultAccount=lab-06`), so the group is preferred and only when there is none
    does it fall back to the configuration's default.
    """
    group = _group_name(entry)
    if group:
        return group
    return str(cfgmod.get(environment.config, "slurm.fallback_account", "hpc-default"))


def _require_user(environment: Any, username: str) -> Dict[str, Any]:
    from ..common.errors import EntryNotFound

    entry = environment.directory.get_user(username)
    if entry is None:
        raise EntryNotFound(t("msg.user.not_found", username=username))
    return entry


def _mail(environment: Any, kind: str, to: Optional[str], send: bool, **context: Any) -> bool:
    """Send the mail when it applies.

    Three reasons not to send: it was not asked for, there is no recipient, or we are in
    simulation. The last one is the important one — `--simulate` walks the whole flow and
    **cannot** send a real mail to a person.
    """
    if not send or not to or environment.mailer is None or environment.dry_run:
        return False
    return environment.mailer.send(kind, to, **context)


def _group_name(entry: Dict[str, Any]) -> Optional[str]:
    """Name of the user's group, or None if only the numeric gid is known."""
    group = resolve_group_label(entry)
    if not group or str(group).startswith("gid:"):
        return None
    return str(group)


def reset_password(environment: Any, username: str, password: Optional[str] = None,
                   send_mail: Optional[bool] = None, notify: bool = True) -> Dict[str, Any]:
    """Set a temporary password and (by default) notify by mail.

    It returns the password in the clear **so the operator reads it on screen**: it is
    the only moment it exists outside the directory. The audit log redacts it.
    """
    entry = _require_user(environment, username)
    new_password = password or generate_secure_password(_password_length(environment))

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        environment.directory.set_password(environment.directory.user_dn(username),
                                           new_password)
        if environment.identity is not None:
            environment.identity.refresh_user(username)

    sent = False
    if notify:
        # The mail carries the temporary password: it is what the person needs to log
        # in. It used to say "it will be delivered through a separate channel" and the
        # person was left waiting.
        sent = _mail(environment, "password", entry.get("mail"),
                     should_send_mail(environment, send_mail), username=username,
                     temp_pass=new_password, group=_group_name(entry))

    if environment.auditor is not None:
        environment.auditor.record(ACTION_RESET_PASSWORD, username,
                                   {"mail_sent": sent}, dry_run=environment.dry_run)

    return {"username": username, "password": new_password, "mail_sent": sent,
            "pending_confirmation": needs_confirmation(environment, send_mail)}


def set_expiry(environment: Any, username: str,
               expires: Optional[datetime.date]) -> Dict[str, Any]:
    """Change **only** the expiry of an account.

    It is the operation that was missing for the bulk case: there are 7 accounts with
    `shadowExpire: 20819` (2027-01-01) that will block themselves, and the only way to
    move them was reactivating one by one —which also changes the password and the
    shell, things that have nothing to do with the date.

    `expires=None` leaves the account permanent (`shadowExpire=-1`), which is how the
    136 active ones in the directory are.
    """
    entry = _require_user(environment, username)
    target = (str(accounts_mod.date_to_shadow_expire(expires)) if expires is not None
              else str(cfgmod.get(environment.config, "cluster.shadow_expire_permanent", -1)))
    previous = str(entry.get("shadowExpire") or "")

    if previous == target:
        return {"username": username, "changed": False, "already": True,
                "shadow_expire": target,
                "state_before": accounts_mod.state(entry),
                "state_after": accounts_mod.state(entry)}

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        environment.directory.update(environment.directory.user_dn(username),
                                     {"shadowExpire": target})
    if environment.auditor is not None:
        environment.auditor.record(ACTION_EXPIRE_SET, username,
                                   {"before": previous or None, "after": target},
                                   dry_run=environment.dry_run)

    return {"username": username, "changed": True, "already": False,
            "shadow_expire": target,
            "state_before": accounts_mod.state(entry),
            "state_after": accounts_mod.state(dict(entry, shadowExpire=target))}


def deactivate_user(environment: Any, username: str, reason: Optional[str] = None,
                    send_mail: Optional[bool] = None, remove_slurm: bool = True,
                    lock_shell: bool = True) -> Dict[str, Any]:
    """Suspend an account: expiry + no-login shell + Slurm + notice.

    The pair `shadowExpire=1` + `/sbin/nologin` is the state the 62 blocked accounts on
    the cluster already have, so the deactivation stays consistent with what is there.
    """
    entry = _require_user(environment, username)
    state_before = accounts_mod.state(entry)
    if accounts_mod.is_blocked(entry):
        return {"username": username, "changed": False, "already_blocked": True,
                "state_before": state_before, "state_after": state_before}

    updates: Dict[str, Any] = {"shadowExpire": "1"}
    if lock_shell:
        updates["loginShell"] = _nologin_shell(environment)

    slurm_before: List[str] = []
    backup: Optional[str] = None
    slurm_removed = False
    if remove_slurm and environment.slurm is not None and environment.slurm.available:
        slurm_before = environment.slurm.associations(username)
        if slurm_before:
            if not environment.dry_run:
                # It is backed up BEFORE removing: if the user belongs to two labs,
                # reactivating later has to give both back.
                backup = environment.slurm.save_associations(username)
                slurm_removed = environment.slurm.remove_user(username)

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        environment.directory.update(environment.directory.user_dn(username), updates)
        if environment.identity is not None:
            environment.identity.refresh_all()

    sent = _mail(environment, "deactivation", entry.get("mail"),
                 should_send_mail(environment, send_mail), username=username, reason=reason)

    if environment.auditor is not None:
        environment.auditor.record(
            ACTION_DEACTIVATE, username,
            {"reason": reason, "slurm_before": slurm_before, "slurm_removed": slurm_removed,
             "slurm_backup": backup, "shell_locked": lock_shell, "mail_sent": sent},
            dry_run=environment.dry_run)

    return {
        "username": username, "changed": True, "already_blocked": False,
        "state_before": state_before,
        "state_after": accounts_mod.state(dict(entry, **updates)),
        "changes": sorted(updates),
        "slurm_before": slurm_before, "slurm_removed": slurm_removed,
        "slurm_backup": backup, "mail_sent": sent,
        "pending_confirmation": needs_confirmation(environment, send_mail),
    }


def reactivate_user(environment: Any, username: str, password: Optional[str] = None,
                    expires: Optional[datetime.date] = None, reset: bool = True,
                    send_mail: Optional[bool] = None, restore_slurm: bool = True) -> Dict[str, Any]:
    """Reactivate an account: shell, expiry, temporary password and Slurm.

    `expires` accepts a date. With no date, the account becomes permanent
    (`shadowExpire=-1`), which is what `activate_user.sh` did.

    `reset=True` generates a new temporary password and returns it to be shown: a
    reactivated account with no valid credentials is useless, and the user's old password
    cannot be recovered from the directory (it is hashed).
    """
    entry = _require_user(environment, username)

    updates: Dict[str, Any] = {"loginShell": _default_shell(environment)}
    if expires is not None:
        updates["shadowExpire"] = str(accounts_mod.date_to_shadow_expire(expires))
    else:
        updates["shadowExpire"] = str(cfgmod.get(environment.config,
                                                 "cluster.shadow_expire_permanent", -1))

    state_before = accounts_mod.state(entry)
    new_password: Optional[str] = None
    if reset:
        new_password = password or generate_secure_password(_password_length(environment))

    if not environment.dry_run:
        environment.directory.save_entry(environment.directory.user_dn(username))
        environment.directory.update(environment.directory.user_dn(username), updates)
        if new_password:
            environment.directory.set_password(environment.directory.user_dn(username),
                                               new_password)
        if environment.identity is not None:
            environment.identity.refresh_all()

    restored_accounts: List[str] = []
    slurm_warning: Optional[str] = None
    if restore_slurm and environment.slurm is not None and environment.slurm.available:
        if not environment.dry_run:
            try:
                restored_accounts = environment.slurm.restore_associations(
                    username, _fallback_account(environment, entry))
            except SlurmError as exc:
                # The mail with the password is what the person needs to log in: a Slurm
                # stumble cannot leave them waiting. It really happened on 2026-10-14
                # with `mibarra`: the account was reactivated in LDAP, with a password
                # nobody knew and **with no warning**, because the command aborted here —
                # before sending the mail.
                slurm_warning = t("msg.reactivate.slurm_warning", error=exc)

    sent = _mail(environment, "reactivation", entry.get("mail"),
                 should_send_mail(environment, send_mail), username=username,
                 temp_pass=new_password or t("msg.no_changes"),
                 group=_group_name(entry),
                 expires=expires.isoformat() if expires else None)

    if environment.auditor is not None:
        environment.auditor.record(
            ACTION_REACTIVATE, username,
            {"expires": expires.isoformat() if expires else None,
             "password_reset": bool(new_password),
             "slurm_accounts": restored_accounts, "slurm_warning": slurm_warning,
             "mail_sent": sent, "password": new_password},
            dry_run=environment.dry_run)

    return {
        "username": username, "changed": True,
        "state_before": state_before,
        "state_after": accounts_mod.state(dict(entry, **updates)),
        "password": new_password, "expires": expires,
        "slurm_accounts": restored_accounts,
        "slurm_warning": slurm_warning,
        "warnings": [[slurm_warning]] if slurm_warning else [],
        "mail_sent": sent, "pending_confirmation": needs_confirmation(environment, send_mail),
    }


def next_expiry(reference: Optional[datetime.date] = None) -> datetime.date:
    """End of year, according to the configuration (`cluster.year_end`).

    It is kept because there is code and tests that use it, but now it **delegates**: the
    date policy lives in `core/expiry.py`, so that no hardcoded rule is left which has to
    be edited and redeployed to change it.
    """
    from ..core import expiry as expiry_mod

    return expiry_mod.next_year_end({}, reference)
