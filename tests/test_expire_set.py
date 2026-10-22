"""`expire-set`: change the expiry date of several accounts, and nothing else.

The case that motivated it: 7 accounts in the real directory have `shadowExpire: 20819`
(2027-01-01) and are about to lock themselves out. Until now the only way to move that
date was `reactivate`, which also **changes the password and the shell** — two things
that have nothing to do with anybody's expiry date.

Watch out for a subtlety that cost one badly written test: moving the date **does not
unblock anybody**. Of the accounts in the directory, 57 are blocked by `loginShell:
/sbin/nologin`, and that block does not depend on the expiry date. To enable a blocked
account there is `reactivate`.
"""

from __future__ import annotations

import datetime

from modules.core import accounts
from modules.testing.fake_services import build_environment
from modules.users import lifecycle


def _user(env, username: str) -> dict:
    return env.directory.get_user(username)


def test_a_date_is_written_as_days_since_1970(config: dict):
    env = build_environment(config)

    result = lifecycle.set_expiry(env, "aalarcon", datetime.date(2027, 1, 1))

    entry = _user(env, "aalarcon")
    assert result["changed"] is True
    assert entry["shadowExpire"] == "20819"
    assert accounts.shadow_expire_date(entry) == datetime.date(2027, 1, 1)


def test_never_leaves_the_account_permanent(config: dict):
    """Same as `reactivate` with no date: `-1`, like the 136 active ones in the directory."""
    env = build_environment(config)

    result = lifecycle.set_expiry(env, "aalarcon", None)

    entry = _user(env, "aalarcon")
    assert result["changed"] is True
    assert entry["shadowExpire"] == "-1"
    assert accounts.shadow_expire_date(entry) is None


def test_the_expiry_does_not_unblock_anybody(config: dict):
    """The date moves; the shell does not.

    `aalarcon` is blocked by `loginShell: /sbin/nologin`, so it stays blocked even when
    its expiry date becomes permanent. That is `reactivate`'s job, and that is why the
    two commands are different.
    """
    env = build_environment(config)
    assert accounts.is_blocked(_user(env, "aalarcon")) is True

    lifecycle.set_expiry(env, "aalarcon", None)

    entry = _user(env, "aalarcon")
    assert entry["shadowExpire"] == "-1"
    assert accounts.is_blocked(entry) is True
    assert "shell de no-login" in accounts.describe(entry)


def test_it_touches_neither_the_password_nor_the_shell(config: dict):
    """What sets `expire-set` apart from `reactivate`: everything else stays the same."""
    env = build_environment(config)
    before = dict(_user(env, "aalarcon"))

    lifecycle.set_expiry(env, "aalarcon", datetime.date(2027, 1, 1))

    after = dict(_user(env, "aalarcon"))
    for attribute in ("userPassword", "loginShell", "gidNumber", "homeDirectory"):
        assert before.get(attribute) == after.get(attribute), attribute


def test_if_it_already_had_that_date_nothing_is_written(config: dict):
    env = build_environment(config)
    lifecycle.set_expiry(env, "aalarcon", datetime.date(2027, 1, 1))
    backups_before = len(env.directory.actions())

    result = lifecycle.set_expiry(env, "aalarcon", datetime.date(2027, 1, 1))

    assert result["changed"] is False and result["already"] is True
    assert len(env.directory.actions()) == backups_before, "it should not even back up"


def test_in_simulation_it_does_not_write(config: dict):
    env = build_environment(config)
    env.dry_run = True
    before = _user(env, "aalarcon").get("shadowExpire")

    result = lifecycle.set_expiry(env, "aalarcon", None)

    assert result["changed"] is True       # the flow says it would do it
    assert _user(env, "aalarcon").get("shadowExpire") == before
    assert env.directory.actions() == []
