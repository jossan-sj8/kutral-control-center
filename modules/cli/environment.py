"""Wiring of the runtime environment, and the guard that avoids false promises.

There are two ways to build the `Environment`, and the difference matters:

  - **`prod`**: real adapters: LDAP directory (`core/ldap_directory.py`), Slurm
    (`core/slurm_admin.py`), identity (`core/identity.py`), storage (`core/storage.py`),
    mail (`core/smtp_mailer.py`), hooks and audit. All of them write to the real cluster.
  - **`lab`**: the doubles from `testing/fake_services.py` over a real sandbox on disk.
    Everything works, nothing touches the cluster.

And that is why `require_adapters` exists: if a real adapter is missing, the command
**refuses with a clear message** instead of doing half the job. A deactivation that
changes LDAP and does not touch Slurm, or that does not refresh the identity cache,
leaves the cluster in a worse state than if nothing had been done — and worse still: it
looks like it worked.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..common.errors import ConfigError
from ..common.i18n import t
from ..core import config as cfgmod
from ..core.audit import AuditLog
from ..core.hooks import ShellHooks
from ..core.ports import Environment

#: Adapter -> message key with what it is needed for, in the operator's words.
ADAPTER_KEYS = {
    "slurm": "adapter.slurm",
    "storage": "adapter.storage",
    "identity": "adapter.identity",
    "mailer": "adapter.mailer",
    "hooks": "adapter.hooks",
}


def adapter_purpose(name: str) -> str:
    """What that adapter is for, in the current language."""
    return t(ADAPTER_KEYS[name]) if name in ADAPTER_KEYS else name


def build_environment(config: Dict[str, Any], simulate: bool = False,
                      interactive: bool = True) -> Environment:
    """Build the environment according to `environment` in the configuration file."""
    if str(config.get("environment", "prod")).lower() == "prod":
        return _build_prod(config, simulate, interactive)
    return _build_lab(config, simulate)


def _build_prod(config: Dict[str, Any], simulate: bool, interactive: bool) -> Environment:
    """Real environment: every adapter writes to the cluster."""
    from ..core.identity import Identity
    from ..core.ldap_directory import LdapDirectory
    from ..core.slurm_admin import SlurmAdmin
    from ..core.smtp_mailer import SmtpMailer
    from ..core.storage import Storage

    directory = LdapDirectory.connect(config, interactive=interactive)
    return Environment(
        config=config,
        directory=directory,
        slurm=SlurmAdmin(config),
        storage=Storage(config),
        identity=Identity(config),
        mailer=SmtpMailer(config),
        auditor=AuditLog(config),
        hooks=ShellHooks(config),
        dry_run=simulate,
    )


def _build_lab(config: Dict[str, Any], simulate: bool) -> Environment:
    """Rehearsal environment: doubles over a real sandbox on disk."""
    from ..testing.fake_services import build_environment as build_fakes

    environment = build_fakes(config, state_path=state_file(config))
    environment.dry_run = simulate
    return environment


def state_file(config: Dict[str, Any]) -> str:
    """Path of the state file of the rehearsal directory.

    It is what makes it possible to chain commands: create an account, and have the next
    command see it. Without it, every invocation would start from the seed.
    """
    from ..core import config as cfgmod

    configurado = cfgmod.path_for(config, "state_file")
    if configurado:
        return configurado
    base = config.get("_base_dir") or os.getcwd()
    return os.path.join(base, "sandbox", "directory.json")


def persist_lab_state(environment: Environment, guardar: bool = True) -> Optional[str]:
    """Save the rehearsal directory when the command ends.

    It does nothing in production (the real adapter has no `save_state`), nor in
    simulation: if it was simulated, what is in memory must not become state.
    """
    if not guardar or environment.dry_run:
        return None
    if not hasattr(environment.directory, "save_state"):
        return None
    return environment.directory.save_state(state_file(environment.config))


def require_adapters(environment: Environment, names: List[str]) -> None:
    """Refuse if an adapter is missing, or if the tool it needs is not there.

    Two different refusals, with two different messages:

    1. The adapter is not wired up (a deployment problem).
    2. `sacctmgr` does not exist on this host. It is the easy one to overlook: the
       adapter is there and the operation "works", but the Slurm steps are skipped
       silently. It is cut off before starting.
    """
    faltan = [name for name in names if getattr(environment, name, None) is None]
    if faltan:
        detalle = "\n".join("  - {}: {}".format(name, adapter_purpose(name))
                            for name in faltan)
        raise ConfigError(t("msg.env.missing_adapters", detail=detalle))

    if "slurm" in names and not getattr(environment.slurm, "available", True):
        raise ConfigError(t("msg.env.no_sacctmgr"))


def describe_environment(environment: Environment) -> Dict[str, Any]:
    """Summary of what the tool is working with. It goes in the header of every output."""
    config = environment.config
    disponibles = {}
    for name in ADAPTER_KEYS:
        port = getattr(environment, name, None)
        if port is None:
            disponibles[name] = t("adapter.state.absent")
        elif type(port).__module__.startswith("modules.testing"):
            disponibles[name] = t("adapter.state.double")
        elif name == "slurm" and not getattr(port, "available", True):
            disponibles[name] = t("adapter.state.real_no_sacctmgr")
        else:
            disponibles[name] = t("adapter.state.real")
    return {
        "environment": config.get("environment"),
        "ldap": config["ldap"]["server"],
        "dry_run": environment.dry_run,
        "send_mail": environment.mail_policy,
        "adapters": disponibles,
        "config_path": config.get("_config_path"),
        "base_dir": config.get("_base_dir"),
    }


def config_summary(config: Dict[str, Any]) -> Dict[str, Any]:
    """Useful data from the configuration, with no secrets."""
    return {
        "environment": config.get("environment"),
        "ldap": config["ldap"]["server"],
        "base_dn": config["ldap"]["base_dn"],
        "group_dn": config["ldap"]["group_dn"],
        "beegfs_home": cfgmod.path_for(config, "beegfs_home"),
        "beegfs_labs": cfgmod.path_for(config, "beegfs_labs"),
        "logs": cfgmod.path_for(config, "logs_dir"),
        "backups": cfgmod.path_for(config, "backups_dir"),
        "mail_transport": cfgmod.get(config, "smtp.transport"),
        "send_mail": cfgmod.get(config, "cluster.send_mail"),
        "hooks": {key: len(value or []) for key, value in (config.get("hooks") or {}).items()},
    }
