"""Configuration: the network guard, the defaults and the password resolution.

It needs PyYAML (it is skipped when PyYAML is not installed, because the rest of the
suite must be able to run on any machine).
"""

from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("yaml", reason="these tests read the real config.yaml files")

from modules.common.errors import ConfigError  # noqa: E402
from modules.core import config as cfgmod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINIMAL_LDAP = """
ldap:
  server: "ldap://{server}"
  base_dn: "ou=People,<SUFIJO_DEL_DIRECTORIO>"
  group_dn: "ou=Group,<SUFIJO_DEL_DIRECTORIO>"
  manager_dn: "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>"
"""


def _write(content: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    handle.write(content)
    handle.close()
    return handle.name


def test_the_configs_of_the_repository_load():
    prod = cfgmod.load_config(os.path.join(ROOT, "config.example.yaml"))
    lab = cfgmod.load_config(os.path.join(ROOT, "config.lab.yaml"))
    assert prod["environment"] == "prod"
    assert lab["environment"] == "lab"
    assert prod["ldap"]["server"] == "ldap://192.0.2.154"
    assert prod["cluster"]["password_scheme"] == "{CRYPT}"


def test_relative_paths_resolve_against_the_config():
    lab = cfgmod.load_config(os.path.join(ROOT, "config.lab.yaml"))
    assert cfgmod.path_for(lab, "beegfs_home").endswith(os.path.join("sandbox", "mnt", "beegfs", "home"))
    assert os.path.isabs(cfgmod.path_for(lab, "logs_dir"))


def test_a_minimal_config_inherits_the_defaults():
    path = _write("environment: dev\n" + MINIMAL_LDAP.format(server="10.0.0.5"))
    try:
        config = cfgmod.load_config(path)
        assert config["cluster"]["send_mail"] == "ask"
        assert config["smtp"]["transport"] == "msmtp"
        assert config["cluster"]["uid_start"] == 1150
        assert config["guard_networks"] == ["192.0.2.0/24"]
    finally:
        os.unlink(path)


def test_the_lab_environment_cannot_point_at_production():
    """The most important guard: it is what stops a write against the real cluster."""
    path = _write("environment: lab\n" + MINIMAL_LDAP.format(server="192.0.2.154"))
    try:
        with pytest.raises(ConfigError) as error:
            cfgmod.load_config(path)
        assert "192.0.2.0/24" in str(error.value)
    finally:
        os.unlink(path)


def test_production_is_allowed_to_point_at_production():
    path = _write("environment: prod\n" + MINIMAL_LDAP.format(server="192.0.2.154"))
    try:
        assert cfgmod.load_config(path)["environment"] == "prod"
    finally:
        os.unlink(path)


@pytest.mark.parametrize("content, expected", [
    ("environment: pruebas\n" + MINIMAL_LDAP.format(server="10.0.0.1"), "environment"),
    ("environment: prod\nldap:\n  server: 'ldap://10.0.0.1'\n  base_dn: x\n  group_dn: y\n", "manager_dn"),
    ("environment: prod\nldap: 'ldap://10.0.0.1'\n", "mapa"),
    ("environment: prod\n" + MINIMAL_LDAP.format(server="10.0.0.1") + "guard_networks: '198.51.100.0/16'\n", "lista"),
    ("environment: prod\n" + MINIMAL_LDAP.format(server="10.0.0.1") + "cluster:\n  send_mail: quizas\n", "send_mail"),
])
def test_invalid_configurations_are_rejected(content, expected):
    # The expected words are the Spanish ones: the suite always runs in `es`.
    path = _write(content)
    try:
        with pytest.raises(ConfigError) as error:
            cfgmod.load_config(path)
        assert expected in str(error.value)
    finally:
        os.unlink(path)


def test_password_from_the_environment_variable(monkeypatch, tmp_path):
    path = _write("environment: dev\n" + MINIMAL_LDAP.format(server="10.0.0.5"))
    try:
        monkeypatch.setenv("KUTRAL_LDAP_PASSWORD", "from-env")
        config = cfgmod.load_config(path)
        assert cfgmod.resolve_ldap_password(config, interactive=False) == "from-env"
    finally:
        os.unlink(path)


def test_password_from_the_file_and_the_permission_warning(tmp_path, capsys, monkeypatch):
    # Without this the test measures something else when the environment already carries
    # the variable: the documented order is environment -> file, and the file is the path
    # this test wants to exercise.
    monkeypatch.delenv("KUTRAL_LDAP_PASSWORD", raising=False)
    secret = tmp_path / "ldap.pass"
    secret.write_text("from-file\n", encoding="utf-8")
    os.chmod(str(secret), 0o644)
    # `password_file` goes INSIDE the ldap block that MINIMAL_LDAP already brings (two
    # spaces). It used to be appended as a second `ldap:` block at the end of the file:
    # YAML keeps the last block and drops server/base_dn/group_dn/manager_dn without a
    # word, so this test never exercised the password-file path at all.
    path = _write("environment: dev\n" + MINIMAL_LDAP.format(server="10.0.0.5")
                  + "  password_file: '" + str(secret).replace("'", "''") + "'\n")
    try:
        config = cfgmod.load_config(path)
        assert config["ldap"]["password_file"] == str(secret)
        assert cfgmod.resolve_ldap_password(config, interactive=False) == "from-file"

        # The warning about loose permissions is part of what the test name promises:
        # it used to take capsys and never look at it.
        mode = os.stat(str(secret)).st_mode & 0o777
        warnings = capsys.readouterr().out
        assert "permisos {:o}".format(mode) in warnings
        assert "chmod 600" in warnings
    finally:
        os.unlink(path)


def test_a_duplicate_key_is_rejected_instead_of_being_lost():
    """YAML keeps the last repeated block; that leaves the config half-configured."""
    path = _write("environment: dev\n" + MINIMAL_LDAP.format(server="10.0.0.5")
                  + "ldap:\n  password_file: '/tmp/ldap.pass'\n")
    try:
        with pytest.raises(ConfigError) as error:
            cfgmod.load_config(path)
        assert "duplicada" in str(error.value)
        assert "'ldap'" in str(error.value)
    finally:
        os.unlink(path)


def test_with_no_password_source_it_fails_clearly():
    path = _write("environment: dev\n" + MINIMAL_LDAP.format(server="10.0.0.5"))
    try:
        config = cfgmod.load_config(path)
        config["ldap"]["password_file"] = None
        with pytest.raises(ConfigError) as error:
            cfgmod.resolve_ldap_password(config, interactive=False)
        assert "KUTRAL_LDAP_PASSWORD" in str(error.value)
    finally:
        os.unlink(path)
