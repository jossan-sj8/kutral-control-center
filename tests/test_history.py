"""The bash history folder: `/mnt/beegfs/backup/history/<user>`.

It came out of a controlled test in production, not out of a guess. When a deleted
account was recreated with the same name and a different uid, the login reported

    -bash: /mnt/beegfs/backup/history/ptest/history_host-gestion: Permission denied

because the folder —which carries the **name** of the user, not their uid— had been left
owned by the previous account, and `ptest` could not write inside it. The inherited
script did not look at it, so the error was dragged along on every login.

The folder is used by `/etc/profile.d/history.sh` on every connection, and until now no
operation of the control center touched it.

Note on the assertions: words such as `historial` come from the message catalog, which
the suite exercises in `es`.
"""

from __future__ import annotations

import os

import pytest

from conftest import POSIX

from modules.common.errors import StorageError
from modules.core.storage import Storage
from modules.testing.fake_services import SandboxStorage, build_environment
from modules.users import creation


def _config(base_dir: str) -> dict:
    """Minimal config: only what Storage reads to locate the three bases."""
    return {
        "_base_dir": base_dir,
        "_config_path": os.path.join(base_dir, "config.yaml"),
        "paths": {"beegfs_home": os.path.join(base_dir, "home"),
                  "beegfs_labs": os.path.join(base_dir, "labs"),
                  "beegfs_history": os.path.join(base_dir, "history")},
    }


def test_it_is_created_where_the_login_expects_it(tmp_path):
    """Outside home and labs, with the mode the shell needs."""
    storage = Storage(_config(str(tmp_path)))
    path = storage.ensure_history("dmunoz", 1272, 9000)

    assert path == os.path.join(str(tmp_path), "history", "dmunoz")
    assert os.path.isdir(path)
    if POSIX:
        # The mode is what the shell needs to write inside; Windows ignores it.
        assert oct(os.stat(path).st_mode & 0o777) == "0o755"
    assert any("historial" in action for action in storage.actions)


def test_the_path_guard_includes_the_history(tmp_path):
    """History lives outside the other two bases: it is added on purpose.

    It is the same guard that stops deleting somebody else's home; if it did not include
    this base, any operation on the history would be out of control.
    """
    storage = Storage(_config(str(tmp_path)))
    assert storage.history_base == os.path.join(str(tmp_path), "history")

    with pytest.raises(StorageError):
        storage._assert_inside_bases("/etc/passwd")
    storage._assert_inside_bases(storage.history("dmunoz"))


def test_it_fixes_the_owner_of_a_deleted_account(tmp_path):
    """The `ptest` case: the folder belonged to uid 1265 and the new account is 1285."""
    storage = SandboxStorage(_config(str(tmp_path)))
    path = storage.ensure_history("ptest", 1265, 9000)
    with open(os.path.join(path, "history_host-gestion"), "w", encoding="utf-8") as handle:
        handle.write("old history\n")

    storage.ensure_history("ptest", 1285, 9100)

    assert storage.ownership_of(path)["uid"] == 1285
    assert storage.ownership_of(path)["gid"] == 9100
    assert storage.ownership_of(path)["mode"] == 0o755


def test_creation_leaves_the_folder_ready(config: dict):
    """That creating the account really calls it, not only the port."""
    env = build_environment(config)
    result = creation.create_user(env, {
        "fullname": "Prueba Historial", "username": "phistorial", "group": "lab-06",
        "mail": "phistorial@ejemplo.cl", "employee_type": "student", "institute": "UOH"})

    path = env.storage.history("phistorial")
    assert os.path.isdir(path)
    assert env.storage.ownership_of(path)["uid"] == result["uid"]
    assert any("historial" in movement for movement in result["movements"])


def test_renaming_moves_the_history_folder(tmp_path):
    """The folder carries the user's name: on rename, it is renamed along with it.

    If it were not moved, the person would start with an empty history and an orphan
    folder with the old name would stay behind, related to nobody.
    """
    storage = SandboxStorage(_config(str(tmp_path)))
    origin = storage.ensure_history("dmunoz", 1272, 9000)
    with open(os.path.join(origin, "history_host-gestion"), "w", encoding="utf-8") as handle:
        handle.write("important history\n")

    destination = storage.move_history("dmunoz", "dmunozs", 1272, 9000)

    assert destination == storage.history("dmunozs")
    assert not os.path.exists(origin), "the old folder must not stay behind"
    assert os.path.exists(os.path.join(destination, "history_host-gestion")), "the history goes with the account"
    assert storage.ownership_of(destination)["uid"] == 1272
