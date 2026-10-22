"""Configuration loading, validation and guards.

Three things it does that the inherited code did not:

1. It merges the defaults with the file, so a short config.yaml is valid and no
   missing key blows up halfway through an operation.
2. It resolves the LDAP Manager password in an explicit order (environment →
   file with permissions → prompt), instead of passing it on the command line.
3. Network guard: if environment != prod, it aborts when the LDAP target falls
   inside a network declared in guard_networks. That is what stops a lab config
   from ending up writing to the real production cluster.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import yaml

from ..common.errors import ConfigError
from ..common.i18n import t

DEFAULTS: Dict[str, Any] = {
    "environment": "prod",
    "ldap": {
        "server": None,
        "base_dn": None,
        "group_dn": None,
        "root_dn": None,
        "manager_dn": None,
        "password_file": None,
        "password_env": "KUTRAL_LDAP_PASSWORD",
        "timeout": 10,
    },
    "paths": {
        "scripts_dir": "../scripts/AddUsers",
        "beegfs_home": "/mnt/beegfs/home",
        "beegfs_labs": "/mnt/beegfs/labs",
        "beegfs_history": "/mnt/beegfs/backup/history",
        "logs_dir": "logs",
        "backups_dir": "backups",
        "tutorial_pdf": "docs/Tutorial_basico_uso_cluster.pdf",
    },
    "smtp": {
        "transport": "msmtp",
        "sender": "hpc@ejemplo.cl",
        "server": "localhost",
        "port": 25,
    },
    "cluster": {
        "name": "Kutral HPC",
        "login_host": "198.51.100.104",
        "web_url": "https://kutral-hpc.ejemplo.cl/",
        "wiki_url": "https://kutral-hpc.ejemplo.cl/mediawiki",
        "default_shell": "/bin/bash",
        "nologin_shell": "/sbin/nologin",
        # Floor of the gid distribution: the lowest gid that may be assigned. It is
        # **not** anybody's group (9000 is `lab-07`'s gid, but that is a
        # coincidence): it only marks where to start looking for the next free one.
        "gid_start": 9000,
        "uid_start": 1150,
        "shadow_expire_permanent": -1,
        "password_scheme": "{CRYPT}",
        "password_length": 12,
        "send_mail": "ask",
    },
    "slurm": {
        "enabled": True,
        "fallback_account": "hpc-default",
        "capture_associations": True,
    },
    "hooks": {"after_create": [], "after_delete": []},
    "guard_networks": ["192.0.2.0/24"],
}

VALID_ENVIRONMENTS = ("prod", "lab", "dev")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override on top of base, recursively for dictionaries."""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader that rejects a repeated key inside the same map.

    PyYAML accepts "ldap:" twice and keeps the last block without saying a word:
    a config.yaml can look complete and be missing ldap.server. A file with
    repeated keys is almost always a bad paste, and a silent error costs more
    than the annoyance of fixing it.
    """

    def construct_mapping(self, node: Any, deep: bool = False) -> Dict[Any, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise yaml.ConstructorError(
                None, None, "expected a mapping, got {}".format(node.id), node.start_mark)
        # The map is inspected as written, before flattening the merged maps
        # (`<<`): repeated there, the key is an error. Keys coming through `<<`
        # may overlap on purpose —flattening puts them first, so the hand-written
        # key still wins, as YAML mandates.
        seen: Dict[Any, Any] = {}
        for key_node, _ in list(node.value):
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConfigError(t("msg.config.duplicate_key", key=key,
                                    path=self.name,
                                    line=key_node.start_mark.line + 1))
            seen[key] = None
        return super().construct_mapping(node, deep=deep)


def load_config(path: str = "config.yaml", apply_guards: bool = True) -> Dict[str, Any]:
    """Load the configuration, apply the defaults and validate it."""
    if not os.path.exists(path):
        raise ConfigError(t("msg.config.not_found", path=path))
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.load(handle, Loader=_NoDuplicateKeysLoader) or {}
    if not isinstance(raw, dict):
        raise ConfigError(t("msg.config.not_a_map", path=path))

    config = _deep_merge(DEFAULTS, raw)
    config["_config_path"] = os.path.abspath(path)
    config["_base_dir"] = os.path.dirname(config["_config_path"])
    config["environment"] = str(config.get("environment", "prod")).lower()

    if config["environment"] not in VALID_ENVIRONMENTS:
        raise ConfigError(t("msg.config.environment_invalid", value=config["environment"],
                            valid=", ".join(VALID_ENVIRONMENTS)))
    _validate(config)
    if apply_guards:
        guard_ldap_target(config)
    return config


def _validate(config: Dict[str, Any]) -> None:
    # A typo like "ldap: ldap://..." (with no sub-keys) used to blow up with
    # AttributeError halfway through an operation. Now it fails at load time.
    for section in ("ldap", "paths", "smtp", "cluster", "slurm", "hooks"):
        if not isinstance(config.get(section), dict):
            raise ConfigError(t("msg.config.section_not_map", section=section,
                                path=config["_config_path"]))
    if not isinstance(config.get("guard_networks"), list):
        raise ConfigError(t("msg.config.guard_networks"))

    ldap = config["ldap"]
    for key in ("server", "base_dn", "group_dn", "manager_dn"):
        if not ldap.get(key):
            raise ConfigError(t("msg.config.missing_key", key=key,
                                path=config["_config_path"]))
    send_mail = config["cluster"].get("send_mail")
    if send_mail not in ("ask", "always", "never"):
        raise ConfigError(t("msg.config.send_mail", value=send_mail))
    if config["smtp"].get("transport") not in ("msmtp", "smtp", "file"):
        raise ConfigError(t("msg.config.transport"))


def guard_ldap_target(config: Dict[str, Any]) -> None:
    """Abort if a non-production environment points at a production network."""
    if config["environment"] == "prod":
        return
    host = ldap_host(config)
    if not host:
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return  # it is a name, not an IP: it gets resolved when connecting
    for network in config.get("guard_networks") or []:
        try:
            if address in ipaddress.ip_network(str(network), strict=False):
                raise ConfigError(t("msg.config.blocked_by_guard",
                                    environment=config["environment"], host=host,
                                    network=network))
        except ValueError:
            continue


def ldap_host(config: Dict[str, Any]) -> Optional[str]:
    """Return the host of ldap.server, without scheme or port."""
    server = config["ldap"].get("server") or ""
    if "://" in server:
        parsed = urlparse(server)
        return parsed.hostname
    return server.split(":")[0] or None


def resolve_path(config: Dict[str, Any], value: Optional[str]) -> Optional[str]:
    """Resolve a relative path against the config file's directory."""
    if not value:
        return None
    if os.path.isabs(value):
        return value
    return os.path.normpath(os.path.join(config["_base_dir"], value))


def path_for(config: Dict[str, Any], key: str) -> str:
    """Shortcut for config['paths'][key], already resolved."""
    return resolve_path(config, config["paths"].get(key)) or ""


def resolve_ldap_password(config: Dict[str, Any], interactive: bool = True) -> str:
    """Obtain the LDAP Manager password.

    Order: the session's environment variable → interactive prompt. The password
    must not be left on disk: `ldap.password_file` still exists, but the
    repository's config.yaml leaves it empty on purpose, and if someone uses it
    anyway there is a warning when the permissions are lax. The configuration file
    never carries the password.
    """
    env_name = config["ldap"].get("password_env") or "KUTRAL_LDAP_PASSWORD"
    from_env = os.environ.get(env_name)
    if from_env:
        return from_env.strip()

    password_file = resolve_path(config, config["ldap"].get("password_file"))
    if password_file and os.path.exists(password_file):
        mode = os.stat(password_file).st_mode & 0o777
        if mode & 0o077:
            from .audit import warn_insecure_permissions  # late import: avoids cycles
            warn_insecure_permissions(password_file, mode)
        with open(password_file, "r", encoding="utf-8") as handle:
            secret = handle.read().strip()
        if secret:
            return secret

    if not interactive:
        raise ConfigError(t("msg.config.password_unavailable", env=env_name))
    import getpass
    # No DN in the text: "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>" in the prompt is noise.
    return getpass.getpass(t("cli.password.prompt"))


def get(config: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """Read a nested key with 'ldap.server' notation."""
    node: Any = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def is_prod(config: Dict[str, Any]) -> bool:
    return config.get("environment") == "prod"
