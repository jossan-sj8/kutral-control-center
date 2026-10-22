"""Reactivating when Slurm fails: the mail goes out anyway.

On 2026-10-14 a student (`mibarra`) wrote asking for access for their thesis. The
reactivation changed the shell and the password in the directory, and then `sacctmgr`
failed — because their group (`pmd2025`) was not a Slurm account. The command aborted
right there, **before** sending the mail: the account was left reactivated with a
password nobody knew about, and with no notice. The person least to blame for a Slurm
mistake is the one waiting for their credentials.

There are two fixes. The first one —creating the Slurm account when it is missing— lives
in the real adapter and is covered by `test_groups_without_slurm`. These tests pin down
the second one: when Slurm fails anyway, the reactivation **warns** and the mail goes out.
"""

from __future__ import annotations

from modules.common.errors import SlurmError
from modules.testing.fake_services import build_environment
from modules.users import lifecycle


def _broken_slurm(env) -> None:
    """Simulates the real failure: `sacctmgr` rejects the association."""
    def boom(*_args, **_kwargs):
        raise SlurmError("sacctmgr failed: This account 'pmd2025' doesn't exist.")

    env.slurm.restore_associations = boom


def test_the_reactivation_continues_when_slurm_fails(config: dict):
    env = build_environment(config)
    _broken_slurm(env)

    result = lifecycle.reactivate_user(env, "aalarcon", send_mail=True)

    # What the person needs: the mail with the password.
    assert result["mail_sent"] is True
    assert env.mailer.kinds()[-1] == "reactivation"
    assert result["password"]
    # And the warning about what was left half done.
    assert result["slurm_warning"] and "Slurm" in result["slurm_warning"]
    # The directory did get reactivated.
    assert env.directory.get_user("aalarcon")["loginShell"] == "/bin/bash"


def test_the_slurm_warning_reaches_the_output(config: dict):
    """The warning goes through `warnings`, which is what the CLI prints with `[!]`."""
    env = build_environment(config)
    _broken_slurm(env)

    result = lifecycle.reactivate_user(env, "aalarcon", send_mail=False)

    assert result["warnings"] == [[result["slurm_warning"]]]


def test_without_failures_there_is_no_warning(config: dict):
    env = build_environment(config)

    result = lifecycle.reactivate_user(env, "aalarcon", send_mail=False)

    assert result["slurm_warning"] is None
    assert result["warnings"] == []
