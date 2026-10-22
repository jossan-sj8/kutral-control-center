"""Lifecycle: deactivate, reactivate and reset a password.

All of these tests run **without a cluster**: the directory is the in-memory fake one,
Slurm is a dictionary, mail is written to a file and identity is a set. That is exactly
what the refactor had to achieve so that this could be tested before touching production.

Note on the assertions: the state labels (`Activo con expiración (LDAP)`) come from the
message catalog, which the suite exercises in `es`.
"""

from __future__ import annotations

import datetime
import os

from modules.core import accounts
from modules.testing.fake_services import build_environment
from modules.users import lifecycle


def _config(base_dir: str, send_mail: str = "never") -> dict:
    return {
        "environment": "lab",
        "ldap": {"server": "ldap://10.20.0.10", "base_dn": "ou=People,<SUFIJO_DEL_DIRECTORIO>",
                 "group_dn": "ou=Group,<SUFIJO_DEL_DIRECTORIO>", "root_dn": "<SUFIJO_DEL_DIRECTORIO>",
                 "manager_dn": "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>"},
        "paths": {"beegfs_home": "sandbox/mnt/beegfs/home",
                  "beegfs_labs": "sandbox/mnt/beegfs/labs",
                  "logs_dir": "sandbox/logs", "backups_dir": "sandbox/backups",
                  "mail_dir": "sandbox/mail"},
        "smtp": {"transport": "file", "sender": "hpc@ejemplo.cl", "server": "localhost", "port": 25},
        "cluster": {"name": "Kutral HPC (LAB)", "login_host": "10.20.0.20",
                    "default_shell": "/bin/bash", "nologin_shell": "/sbin/nologin",
                    "default_gid": 9000, "uid_start": 1150, "shadow_expire_permanent": -1,
                    "password_scheme": "{CRYPT}", "password_length": 12, "send_mail": send_mail},
        "slurm": {"enabled": True, "fallback_account": "hpc-default", "capture_associations": True},
        "hooks": {"after_create": [], "after_delete": []},
        "guard_networks": ["192.0.2.0/24"],
        "_base_dir": base_dir, "_config_path": os.path.join(base_dir, "config.lab.yaml"),
    }


def _env(tmp_path, send_mail: str = "never", **kwargs):
    return build_environment(_config(str(tmp_path), send_mail), **kwargs)


def _an_active_user(env) -> dict:
    """An **active** user.

    The first one in the seed is no good: the 62 blocked accounts come first on purpose
    (the `position < BLOCKED_USERS` parameter), and deactivating an account that is
    already blocked is —correctly— a no-op. Using the first one made the test measure the
    wrong path.
    """
    return [u for u in env.directory.list_users() if not accounts.is_blocked(u)][0]


# ---------------------------------------------------------------------------
# Deactivating
# ---------------------------------------------------------------------------

def test_deactivation_leaves_both_block_markers(tmp_path):
    env = _env(tmp_path)
    user = _an_active_user(env)
    result = lifecycle.deactivate_user(env, user["uid"])

    updated = env.directory.get_user(user["uid"])
    assert updated["shadowExpire"] == "1"
    assert updated["loginShell"] == "/sbin/nologin"
    assert accounts.is_blocked(updated)
    assert result["changed"] is True
    assert result["state_before"] != result["state_after"]


def test_deactivation_writes_the_rollback_ldif_before_touching_the_entry(tmp_path):
    """The order matters: touch it first and there is nothing left to back up."""
    env = _env(tmp_path)
    user = _an_active_user(env)
    lifecycle.deactivate_user(env, user["uid"])
    assert env.directory.actions() == ["save_entry", "update"]


def test_deactivation_saves_the_associations_before_removing_them(tmp_path):
    env = _env(tmp_path)
    user = _an_active_user(env)
    env.slurm.users[user["uid"]] = ["lab-06", "lab-07"]

    result = lifecycle.deactivate_user(env, user["uid"])

    assert result["slurm_before"] == ["lab-06", "lab-07"]
    assert result["slurm_removed"] is True
    assert env.slurm.saved[user["uid"]] == ["lab-06", "lab-07"]
    actions = [item[0] for item in env.slurm.calls]
    assert actions.index("save_associations") < actions.index("remove_user")


def test_deactivating_an_already_blocked_account_does_nothing(tmp_path):
    env = _env(tmp_path)
    blocked = [u for u in env.directory.list_users() if accounts.is_blocked(u)][0]
    result = lifecycle.deactivate_user(env, blocked["uid"])
    assert result["already_blocked"] is True
    assert result["changed"] is False
    assert env.directory.actions() == []


# ---------------------------------------------------------------------------
# Reactivating
# ---------------------------------------------------------------------------

def test_reactivation_returns_a_temporary_password_and_applies_it(tmp_path):
    env = _env(tmp_path)
    blocked = [u for u in env.directory.list_users() if accounts.is_blocked(u)][0]

    result = lifecycle.reactivate_user(env, blocked["uid"])

    assert result["password"] and len(result["password"]) == 12
    updated = env.directory.get_user(blocked["uid"])
    assert not accounts.is_blocked(updated)
    assert updated["loginShell"] == "/bin/bash"
    assert updated["shadowExpire"] == "-1"
    assert updated["userPassword"].startswith("{CRYPT}$6$")
    assert result["password"] not in updated["userPassword"], "it must not stay in clear text"


def test_reactivation_with_a_date_writes_the_exact_day(tmp_path):
    """It is what `activate_user.sh` computed and never applied."""
    env = _env(tmp_path)
    blocked = [u for u in env.directory.list_users() if accounts.is_blocked(u)][0]

    result = lifecycle.reactivate_user(env, blocked["uid"],
                                       expires=datetime.date(2027, 1, 1))

    assert env.directory.get_user(blocked["uid"])["shadowExpire"] == "20819"
    assert result["state_after"] == "Activo con expiración (LDAP)"
    assert result["expires"] == datetime.date(2027, 1, 1)


def test_end_of_year_is_january_first_of_the_next_year(tmp_path):
    assert lifecycle.next_expiry(datetime.date(2026, 10, 7)) == datetime.date(2027, 1, 1)
    assert lifecycle.next_expiry(datetime.date(2027, 3, 1)) == datetime.date(2028, 1, 1)


def test_reactivation_brings_back_all_the_slurm_accounts(tmp_path):
    """A user of two labs must not lose the second one when reactivated.

    The real path is: active account with two Slurm accounts -> it is deactivated (they
    are saved and removed) -> it is reactivated and both have to come back.
    """
    env = _env(tmp_path)
    uid = _an_active_user(env)["uid"]
    env.slurm.users[uid] = ["lab-06", "lab-07"]

    lifecycle.deactivate_user(env, uid)
    assert env.slurm.associations(uid) == []

    result = lifecycle.reactivate_user(env, uid)
    assert sorted(result["slurm_accounts"]) == ["lab-06", "lab-07"]
    assert sorted(env.slurm.associations(uid)) == ["lab-06", "lab-07"]


def test_reactivation_without_reset_does_not_touch_the_password(tmp_path):
    env = _env(tmp_path)
    blocked = [u for u in env.directory.list_users() if accounts.is_blocked(u)][0]
    before = env.directory.get_user(blocked["uid"])["userPassword"]

    result = lifecycle.reactivate_user(env, blocked["uid"], reset=False)

    assert result["password"] is None
    assert env.directory.get_user(blocked["uid"])["userPassword"] == before


# ---------------------------------------------------------------------------
# Passwords and mail
# ---------------------------------------------------------------------------

def test_reset_password_returns_the_password_and_stores_it_hashed(tmp_path):
    env = _env(tmp_path)
    user = _an_active_user(env)

    result = lifecycle.reset_password(env, user["uid"])

    assert result["password"] not in env.directory.get_user(user["uid"])["userPassword"]
    assert env.directory.get_user(user["uid"])["userPassword"].startswith("{CRYPT}$6$")


def test_the_mail_policy_is_respected(tmp_path):
    # never: nothing is sent
    env = _env(tmp_path, send_mail="never")
    user = _an_active_user(env)
    lifecycle.deactivate_user(env, user["uid"])
    assert env.mailer.calls == []

    # always: it is sent, and with the right template
    env_always = _env(tmp_path / "b", send_mail="always")
    user_always = _an_active_user(env_always)
    result = lifecycle.deactivate_user(env_always, user_always["uid"])
    assert result["mail_sent"] is True
    assert env_always.mailer.kinds() == ["deactivation"]

    # ask: nothing is sent by default, but it is flagged to be asked about
    env_ask = _env(tmp_path / "c", send_mail="ask")
    user_ask = _an_active_user(env_ask)
    result_ask = lifecycle.deactivate_user(env_ask, user_ask["uid"])
    assert result_ask["pending_confirmation"] is True
    assert env_ask.mailer.calls == []


def test_reactivation_is_announced_by_mail_with_the_password(tmp_path):
    env = _env(tmp_path, send_mail="always")
    blocked = [u for u in env.directory.list_users() if accounts.is_blocked(u)][0]

    result = lifecycle.reactivate_user(env, blocked["uid"],
                                       expires=datetime.date(2027, 1, 1))

    assert env.mailer.kinds() == ["reactivation"]
    sent = env.mailer.last()
    assert sent["context"]["temp_pass"] == result["password"]
    assert sent["context"]["expires"] == "2027-01-01"


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def test_simulation_touches_nothing(tmp_path):
    env = _env(tmp_path, send_mail="always")
    env.dry_run = True
    blocked = [u for u in env.directory.list_users() if accounts.is_blocked(u)][0]
    before = env.directory.get_user(blocked["uid"])

    result = lifecycle.reactivate_user(env, blocked["uid"])

    assert result["changed"] is True                  # it reports what it would do
    assert env.directory.actions() == []              # but nothing was executed
    assert env.directory.get_user(blocked["uid"]) == before
    assert env.slurm.calls == []
    assert env.mailer.calls == []                     # and it writes to nobody
