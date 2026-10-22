"""A group can exist in the directory and **not** be a Slurm account.

It happened in production on 2026-10-14, with `uprueba`: the `change-group` to
`gprueba2` left the directory changed and the command **ended in an error**, because
`gprueba2` was not a Slurm account (the four `gprueba*` on the cluster are like that:
group in LDAP, no account).

Creation (`create-user`, `group-create`) does create the account when it is missing. The
other two paths assumed it was already there:

  - `change-group`: it failed **after** writing to LDAP, and the operator had no way to
    know which half had been done.
  - `group-delete`: it would have failed **after** deleting the directory entry, that is,
    a half-done deletion plus an error on screen.

These tests pin down both: the account is created when it is missing, and it is only
deleted when it exists.
"""

from __future__ import annotations

from modules.groups import deletion_group
from modules.testing.fake_services import build_environment
from modules.users import modification


def test_change_group_creates_the_slurm_account_when_it_is_missing(config: dict):
    env = build_environment(config)
    env.slurm.accounts.discard("lab-06")
    assert env.slurm.account_exists("lab-06") is False

    result = modification.change_group(env, "aalarcon", "lab-06")

    assert ("create_account", "lab-06") in env.slurm.calls
    assert ("register_user", "aalarcon", "lab-06") in env.slurm.calls
    assert result["slurm_warning"] is None
    assert env.directory.get_user("aalarcon")["departmentNumber"] == "lab-06"


def test_group_delete_does_not_try_to_drop_an_account_that_does_not_exist(config: dict):
    env = build_environment(config)
    env.slurm.accounts.discard("lab-06")

    result = deletion_group.delete_group(env, "lab-06", force=True, drop_slurm=True)

    assert result["deleted"] is True
    assert result["slurm_account_removed"] is False
    assert not any(call[0] == "delete_account" for call in env.slurm.calls)
    assert env.directory.get_group("lab-06") is None


def test_group_delete_does_drop_the_account_when_it_exists(config: dict):
    """The other side of the same coin: when the account is there, it gets deleted."""
    env = build_environment(config)
    env.slurm.accounts.add("lab-06")

    result = deletion_group.delete_group(env, "lab-06", force=True, drop_slurm=True)

    assert ("delete_account", "lab-06") in env.slurm.calls
    assert result["slurm_account_removed"] is True
