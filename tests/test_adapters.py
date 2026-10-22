"""The three real adapters: Slurm, identity and storage.

This is the only part of the project that **cannot be tested against the cluster from
here**, so everything that can be tested is tested:

  - **The commands that get built.** The executor is injectable, so a fake runner
    captures the exact argument list of every `sacctmgr` and `sss_cache` call. That
    validates what carries the most risk: the shape of the command and the parsing of
    its output.
  - **The parsing of `sacctmgr`** (`-n -P`, pipe-separated, with repeated lines that
    have to be de-duplicated).
  - **Resolution through `nsswitch`**, with a fake `/etc/passwd`: the difference
    between "it exists locally" and "SSSD resolves it" is the key to the whole deletion
    problem.
  - **The real storage layer**, over a temporary tree: modes, setgid, symlink, move and
    archiving. Including the guard that prevents deleting outside the bases.
"""

from __future__ import annotations

import os

from conftest import POSIX

from modules.common.errors import SlurmError, StorageError
from modules.core.identity import Identity
from modules.core.slurm_admin import SlurmAdmin
from modules.core.storage import Storage


def _config(base_dir: str) -> dict:
    return {
        "environment": "prod",
        "ldap": {"server": "ldap://192.0.2.154", "base_dn": "ou=People,<SUFIJO_DEL_DIRECTORIO>",
                 "group_dn": "ou=Group,<SUFIJO_DEL_DIRECTORIO>", "manager_dn": "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>"},
        "paths": {"beegfs_home": os.path.join(base_dir, "home"),
                  "beegfs_labs": os.path.join(base_dir, "labs"),
                  "logs_dir": os.path.join(base_dir, "logs"),
                  "backups_dir": os.path.join(base_dir, "backups")},
        "smtp": {"transport": "msmtp", "sender": "hpc@ejemplo.cl"},
        "cluster": {"name": "Kutral HPC", "default_shell": "/bin/bash",
                    "nologin_shell": "/sbin/nologin", "password_scheme": "{CRYPT}",
                    "password_length": 12, "send_mail": "never"},
        "slurm": {"fallback_account": "hpc-default"},
        "hooks": {}, "guard_networks": [],
        "_base_dir": base_dir, "_config_path": os.path.join(base_dir, "config.yaml"),
    }


class FakeRunner:
    """Captures the commands and returns prepared answers."""

    def __init__(self, responses=None, default=(0, "", "")):
        self.responses = responses or {}
        self.default = default
        self.commands = []

    def __call__(self, args):
        self.commands.append(list(args))
        key = " ".join(args[1:])
        for pattern, response in self.responses.items():
            if pattern in key:
                return response
        return self.default


# ---------------------------------------------------------------------------
# Slurm
# ---------------------------------------------------------------------------

def test_the_slurm_commands_are_the_inherited_ones(tmp_path):
    """The shapes come from your own scripts, and there are two creation paths.

    - **new** user: a single order, with `DefaultAccount` (that is what `add_users.sh`
      does);
    - **already existing** user: `add user` fails, so the association has to be added
      and the default account set afterwards.
    """
    config = _config(str(tmp_path))

    new_user = FakeRunner({"show user": (0, "", "")})
    SlurmAdmin(config, runner=new_user, available=True).register_user("ptest", "lab-06")
    assert any("DefaultAccount=lab-06" in " ".join(c) for c in new_user.commands)
    assert not [c for c in new_user.commands if "update" in c], "a new user is not updated"

    existing = FakeRunner({"show user": (0, "iprado|\n", "")})
    admin = SlurmAdmin(config, runner=existing, available=True)
    admin.register_user("iprado", "lab-07")
    assert any("add" in c and "account=lab-07" in c for c in existing.commands)
    assert any("set" in c and "DefaultAccount=lab-07" in " ".join(c)
               for c in existing.commands)

    admin.remove_user("iprado")
    assert any(c[1:] == ["-i", "remove", "user", "name=iprado"] for c in existing.commands)


def test_an_account_is_detected_from_its_output(tmp_path):
    present = SlurmAdmin(_config(str(tmp_path)),
                         runner=FakeRunner({"show account": (0, "kutral-lab|\n", "")}),
                         available=True)
    absent = SlurmAdmin(_config(str(tmp_path)),
                        runner=FakeRunner({"show account": (0, "", "")}), available=True)
    assert present.account_exists("kutral-lab") is True
    assert absent.account_exists("kutral-lab") is False


def test_associations_are_de_duplicated(tmp_path):
    output = "lab-06|\nlab-07|\nlab-06|\n\n"
    admin = SlurmAdmin(_config(str(tmp_path)),
                       runner=FakeRunner({"show assoc": (0, output, "")}), available=True)
    assert admin.associations("iprado") == ["lab-06", "lab-07"]


def test_registering_an_existing_user_adds_and_sets_the_account(tmp_path):
    """With an existing user, `add user` fails: the association has to be added and then
    the default account set. This is the shape that has to be confirmed in the canary."""
    runner = FakeRunner({"show user": (0, "iprado|\n", "")})
    admin = SlurmAdmin(_config(str(tmp_path)), runner=runner, available=True)
    assert admin.user_exists("iprado") is True, "the -P output carries 'iprado|'"

    admin.register_user("iprado", "lab-07")

    assert any(c[1:3] == ["-i", "add"] and "account=lab-07" in c for c in runner.commands)
    assert any("DefaultAccount=lab-07" in " ".join(c) for c in runner.commands)


def test_a_slurm_failure_raises_an_error(tmp_path):
    admin = SlurmAdmin(_config(str(tmp_path)),
                       runner=FakeRunner(default=(1, "", "boom")), available=True)
    try:
        admin.create_account("kutral-lab")
        raise AssertionError("it had to raise SlurmError")
    except SlurmError as exc:
        assert "boom" in str(exc) or "sacctmgr" in str(exc)


def test_associations_are_backed_up_and_restored(tmp_path):
    """The backup is what prevents losing laboratories when an account is disabled."""
    config = _config(str(tmp_path))
    runner = FakeRunner({"show assoc": (0, "lab-06|\nlab-07|\n", ""),
                         "show user": (0, "iprado|\n", "")})
    admin = SlurmAdmin(config, runner=runner, available=True)

    path = admin.save_associations("iprado")
    assert os.path.exists(path)
    if POSIX:
        assert oct(os.stat(path).st_mode & 0o777) == "0o600", "it carries data: mode 600"
    assert admin.load_saved_associations("iprado") == ["lab-06", "lab-07"]

    runner.commands.clear()
    restored = admin.restore_associations("iprado", "hpc-default")
    assert restored == ["lab-06", "lab-07"]
    # One `add user` per restored account…
    assert len([c for c in runner.commands if "add" in c and "user" in c]) == 2
    # …and, if the Slurm account did not exist, it is created too: a group may live in
    # the directory and not be a Slurm account (`gprueba2`, `pmd2025`). Without this,
    # `add user` fails and the person is left with no laboratories —and on a
    # reactivation with no mail either, because the command aborted before sending it.
    assert len([c for c in runner.commands if "add" in c and "account" in c]) == 2


def test_without_a_backup_the_fallback_account_is_used(tmp_path, capsys):
    runner = FakeRunner({"show user": (0, "iprado|\n", "")})
    admin = SlurmAdmin(_config(str(tmp_path)), runner=runner, available=True)
    restored = admin.restore_associations("iprado", "hpc-default")
    assert restored == ["hpc-default"]
    # And it says so out loud: in silence, the person goes back to hpc-default and
    # everybody believes they got their laboratory back.
    warning = capsys.readouterr().out
    assert "No hay respaldo de Slurm" in warning and "hpc-default" in warning


def test_available_reports_what_the_host_has(tmp_path):
    assert SlurmAdmin(_config(str(tmp_path)), available=True).available is True
    assert SlurmAdmin(_config(str(tmp_path)), binary="no-existe-esta-orden").available is False


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def _test_passwd(tmp_path, lines) -> str:
    path = os.path.join(str(tmp_path), "passwd")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def test_the_local_account_is_read_from_the_file_not_from_getent(tmp_path):
    """The key difference: `getent` would include the LDAP users."""
    passwd = _test_passwd(tmp_path, [
        "root:x:0:0:root:/root:/bin/bash",
        "iprado:x:1105:9000:Ivan Prado:/mnt/beegfs/home/iprado:/bin/sh",
        "ptest:x:1266:9000:usuario test:/mnt/beegfs/home/ptest:/bin/bash",
    ])
    identity = Identity(_config(str(tmp_path)), passwd_path=passwd)

    assert identity.local_account_exists("iprado") is True
    assert identity.local_account_exists("demo001") is False
    assert sorted(identity.local_accounts()) == ["iprado", "ptest"]


def test_resolving_flags_the_local_source(tmp_path):
    passwd = _test_passwd(tmp_path, [
        "iprado:x:1105:9000:Ivan Prado:/mnt/beegfs/home/iprado:/bin/sh"])
    # The runner receives the full argv; the key is looked up inside args[1:].
    runner = FakeRunner({"passwd iprado": (
        0, "iprado:x:1105:9000:Ivan Prado:/mnt/beegfs/home/iprado:/bin/sh\n", "")})
    identity = Identity(_config(str(tmp_path)), runner=runner, passwd_path=passwd)

    resolved = identity.resolve("iprado")

    assert resolved["uid"] == "1105" and resolved["shell"] == "/bin/sh"
    assert resolved["source"] == "local", "it is in /etc/passwd: that is the problem"


def test_resolving_with_no_result_returns_none(tmp_path):
    passwd = _test_passwd(tmp_path, ["root:x:0:0:root:/root:/bin/bash"])
    runner = FakeRunner(default=(2, "", "no encontrado"))
    identity = Identity(_config(str(tmp_path)), runner=runner, passwd_path=passwd)
    assert identity.resolve("nadie") is None


def test_the_refresh_uses_the_sss_cache_flags(tmp_path):
    runner = FakeRunner()
    identity = Identity(_config(str(tmp_path)), runner=runner,
                        passwd_path=os.path.join(str(tmp_path), "passwd"))

    identity.refresh_all()
    identity.refresh_group("lab-06")
    identity.refresh_user("iprado")

    assert ["sss_cache", "-E"] in runner.commands
    assert ["sss_cache", "-g", "lab-06"] in runner.commands
    assert ["sss_cache", "-u", "iprado"] in runner.commands


def test_a_failed_refresh_warns_but_does_not_break(tmp_path):
    """A failed refresh leaves a stale cache behind: that has to be known, not aborted."""
    runner = FakeRunner(default=(1, "", "no sos root"))
    identity = Identity(_config(str(tmp_path)), runner=runner,
                        passwd_path=os.path.join(str(tmp_path), "passwd"))
    assert identity.refresh_all() is False


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def test_creating_the_home_with_its_mode(tmp_path):
    storage = Storage(_config(str(tmp_path)))
    path = storage.ensure_home("dmunoz", 1272, 9000)

    assert os.path.isdir(path)
    if POSIX:
        assert oct(os.stat(path).st_mode & 0o777) == "0o750"


def test_creating_the_lab_with_setgid(tmp_path):
    """2770 with setgid: that is what makes files inherit the group."""
    storage = Storage(_config(str(tmp_path)))
    path = storage.ensure_lab("lab-06", 9000)

    assert os.path.isdir(path)
    if POSIX:
        assert os.stat(path).st_mode & 0o7777 == 0o2770
        assert os.stat(path).st_mode & 0o2000, "the setgid bit has to be there"


def test_the_link_to_the_lab(tmp_path):
    storage = Storage(_config(str(tmp_path)))
    storage.ensure_home("dmunoz", 1272, 9000)
    storage.ensure_lab("lab-06", 9000)
    try:
        link = storage.ensure_group_link("dmunoz", "lab-06", 1272, 9000)
    except OSError:
        return      # this filesystem does not support symlinks: not tested
    assert os.path.islink(link)
    assert os.readlink(link) == storage.lab("lab-06")


def test_moving_the_home_on_a_rename(tmp_path):
    storage = Storage(_config(str(tmp_path)))
    storage.ensure_home("dmunoz", 1272, 9000)
    with open(os.path.join(storage.home("dmunoz"), "datos.txt"), "w") as handle:
        handle.write("algo")

    target = storage.move_home("dmunoz", "dmunozs", 1272, 9000)

    assert os.path.isdir(target)
    assert not os.path.exists(storage.home("dmunoz"))
    assert os.path.exists(os.path.join(target, "datos.txt")), "the contents travel with it"


def test_archiving_and_removing_the_home(tmp_path):
    storage = Storage(_config(str(tmp_path)))
    path = storage.ensure_home("dmunoz", 1272, 9000)
    with open(os.path.join(path, "datos.txt"), "w") as handle:
        handle.write("contenido importante")

    archive = storage.archive_home("dmunoz", path)
    assert os.path.exists(archive) and archive.endswith(".tar.gz")

    storage.remove_home(path)
    assert not os.path.exists(path)

    import tarfile
    with tarfile.open(archive, "r:gz") as bundle:
        assert bundle.getnames() == ["dmunoz", "dmunoz/datos.txt"]


def test_nothing_is_deleted_outside_the_bases(tmp_path):
    """The guard that prevents an `rm -rf` on the wrong path."""
    storage = Storage(_config(str(tmp_path)))
    outside = os.path.join(str(tmp_path), "otra-cosa")
    os.makedirs(outside, exist_ok=True)

    try:
        storage.remove_home(outside)
        raise AssertionError("it had to refuse to delete outside the bases")
    except StorageError as exc:
        assert "seguridad" in str(exc)
    assert os.path.isdir(outside), "it must not have touched anything"


def test_the_whole_base_is_not_deleted(tmp_path):
    storage = Storage(_config(str(tmp_path)))
    os.makedirs(storage.home_base, exist_ok=True)
    try:
        storage.remove_home(storage.home_base)
        raise AssertionError("it had to refuse to delete the base")
    except StorageError:
        pass
    assert os.path.isdir(storage.home_base)


def test_describing_the_storage_layer(tmp_path):
    storage = Storage(_config(str(tmp_path)))
    storage.ensure_lab("lab-06", 9000)
    summary = storage.describe()
    assert summary["labs_base"].endswith("labs")
    assert "lab " in " ".join(summary["actions"])
