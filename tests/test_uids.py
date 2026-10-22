"""The uids of deleted accounts are never handed out again.

The bash history folder and the orphan files left behind in BeeGFS carry the
**number**, not the name. With the "highest in use + 1" policy, the uid of the last
deleted account came around again, and the new account inherited ownership of whatever
the previous one had left behind.

It really happened in the controlled test of 2026-10-13: `ptest` (uid 1285) was deleted
and the next account, `guion1`, was given the same 1285 — history folder included.
"""

from __future__ import annotations

from conftest import POSIX

from modules.core.ldap_directory import LdapDirectory
from modules.testing.fake_services import build_environment
from modules.users import creation, deletion

ACCOUNT = {"fullname": "Prueba Uid", "group": "lab-06", "mail": "puid@ejemplo.cl",
           "employee_type": "student", "institute": "UOH"}


def _create(env, username: str) -> dict:
    return creation.create_user(env, dict(ACCOUNT, username=username))


def test_the_uid_of_a_deleted_account_is_not_handed_out_again(config: dict):
    env = build_environment(config)
    expected = env.directory.next_uid()

    first = _create(env, "puid1")
    assert first["uid"] == expected

    deletion.delete_user(env, "puid1")

    assert first["uid"] in env.directory.retired_uids()
    assert env.directory.next_uid() > first["uid"]
    assert _create(env, "puid2")["uid"] == first["uid"] + 1


def test_the_ledger_is_a_file_and_never_duplicates_entries(tmp_path):
    """It lives in `backups_dir`, outside the repository: it survives a redeploy,
    which is exactly when it is needed the most."""
    config = {"ldap": {"base_dn": "ou=People,<SUFIJO_DEL_DIRECTORIO>",
                       "group_dn": "ou=Group,<SUFIJO_DEL_DIRECTORIO>"},
              "cluster": {}}
    directory = LdapDirectory(config, None, backups_dir=str(tmp_path))

    assert directory.retired_uids() == []
    directory.retire_uid(1285, "ptest")
    directory.retire_uid(1285, "ptest again")           # no duplicate is recorded
    directory.retire_uid(None)                          # garbage: ignored

    assert directory.retired_uids() == [1285]
    ledger = tmp_path / "uids-retirados.txt"
    assert ledger.read_text(encoding="utf-8").startswith("1285 ptest ")
    if POSIX:
        # The mode is part of the promise —the ledger holds the uids of accounts that are
        # gone— and the cluster is POSIX. Windows does not honour it.
        assert oct(ledger.stat().st_mode & 0o777) == "0o600"
