"""Shared fixtures.

The level-1 tests run **without LDAP, without Slurm and without network**: the
directory is the in-memory fake one and the configuration is built as a plain
dictionary, so the suite works even when PyYAML is not installed.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: File modes (600, 750, 2770) are a POSIX concept: Windows ignores them —its `chmod`
#: only toggles the read-only bit—, so the checks that pin them down are skipped there
#: and run where the tool actually lives: the cluster (AlmaLinux) and any Linux CI.
#: The sandbox storage keeps the modes in memory, so those tests do run everywhere.
POSIX = os.name == "posix"

from modules.common import i18n  # noqa: E402
from modules.testing.fake_directory import FakeDirectory  # noqa: E402
from modules.testing.seed import build_seed  # noqa: E402


def lab_config() -> dict:
    """Same shape as config.lab.yaml, without depending on PyYAML or the disk."""
    return {
        "environment": "lab",
        "ldap": {
            "server": "ldap://10.20.0.10",
            "base_dn": "ou=People,<SUFIJO_DEL_DIRECTORIO>",
            "group_dn": "ou=Group,<SUFIJO_DEL_DIRECTORIO>",
            "root_dn": "<SUFIJO_DEL_DIRECTORIO>",
            "manager_dn": "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>",
            "password_env": "KUTRAL_LDAP_PASSWORD",
            "timeout": 10,
        },
        "paths": {
            "beegfs_home": "sandbox/mnt/beegfs/home",
            "beegfs_labs": "sandbox/mnt/beegfs/labs",
            "beegfs_history": "sandbox/mnt/beegfs/backup/history",
            "logs_dir": "sandbox/logs",
            "backups_dir": "sandbox/backups",
            "tutorial_pdf": "docs/Tutorial_basico_uso_cluster.pdf",
        },
        "smtp": {"transport": "file", "sender": "hpc@ejemplo.cl", "server": "localhost", "port": 25},
        "cluster": {
            "name": "Kutral HPC (LAB)",
            "login_host": "10.20.0.20",
            "default_shell": "/bin/bash",
            "nologin_shell": "/sbin/nologin",
            "gid_start": 9000,
            "uid_start": 1150,
            "shadow_expire_permanent": -1,
            "password_scheme": "{CRYPT}",
            "password_length": 12,
            "send_mail": "never",
        },
        "slurm": {"enabled": True, "fallback_account": "hpc-default", "capture_associations": True},
        "hooks": {"after_create": [], "after_delete": []},
        "guard_networks": ["192.0.2.0/24"],
        "_base_dir": ROOT,
        "_config_path": os.path.join(ROOT, "config.lab.yaml"),
    }


@pytest.fixture
def config() -> dict:
    return lab_config()


@pytest.fixture
def directory(config) -> FakeDirectory:
    """Fake directory preloaded with the 214 synthetic accounts."""
    return FakeDirectory(config, build_seed(config))


@pytest.fixture
def empty_directory(config) -> FakeDirectory:
    """Empty fake directory: useful to exercise the error paths."""
    return FakeDirectory(config, {})


@pytest.fixture(autouse=True)
def suite_language(monkeypatch):
    """The suite always runs in Spanish, whatever the machine's locale says.

    Without this, the messages would be tested in the language of whoever runs the
    tests, and the text assertions would fail on an English machine.
    """
    monkeypatch.setenv(i18n.ENVIRONMENT_VARIABLE, "es")
    i18n.set_language("es")
    yield
    i18n.set_language("es")
