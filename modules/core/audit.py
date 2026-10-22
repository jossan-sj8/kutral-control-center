"""Audit trail of the control center's operations.

Two different things:

- `AuditLog.record(...)`: leaves a trace of who did what and when, in JSONL (one
  JSON line per operation). It is what makes it possible to answer "who deleted
  that account?" six months later.
- `warn_insecure_permissions(...)`: warns when the file holding the LDAP Manager
  password can be read by other users.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..common import ui
from ..common.i18n import t
from . import config as cfgmod


def warn_insecure_permissions(path: str, mode: int) -> None:
    """Warn (without aborting) if the secret file has lax permissions."""
    ui.warn(t("msg.audit.insecure_permissions", path=path, mode="{:o}".format(mode)))
    ui.warn(t("msg.audit.chmod_hint", path=path))


class AuditLog(object):
    """Real implementation of the Auditor port."""

    def __init__(self, config: Dict[str, Any], operator: Optional[str] = None) -> None:
        self.config = config
        self.logs_dir = cfgmod.path_for(config, "logs_dir") or "logs"
        self.operator = operator or _current_operator()
        self.environment = config.get("environment", "prod")
        self.dry_run_flag = False

    def _path(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m")
        return os.path.join(self.logs_dir, "audit-{}.jsonl".format(stamp))

    def record(self, action: str, target: str, details: Optional[Dict[str, Any]] = None,
               result: str = "ok", dry_run: bool = False) -> None:
        """Append one line to the audit log. It never interrupts the operation."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "operator": self.operator,
            "host": socket.gethostname(),
            "environment": self.environment,
            "action": action,
            "target": target,
            "result": result,
            "dry_run": bool(dry_run),
        }
        if details:
            entry["details"] = _redact(details)
        try:
            path = self._path()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            ui.warn(t("msg.audit.write_failed", error=exc))


class NullAuditor(object):
    """Auditor that writes nothing. Useful in tests and simulations."""

    def record(self, action: str, target: str, details: Optional[Dict[str, Any]] = None,
               result: str = "ok", dry_run: bool = False) -> None:
        return None


def _current_operator() -> str:
    try:
        return "{}@{}".format(getpass.getuser(), socket.gethostname())
    except Exception:  # pragma: no cover
        return t("msg.audit.operator_unknown")


SECRET_KEYS = ("password", "userpassword", "pass", "secret", "bind_password", "authtok")


def _redact(details: Dict[str, Any]) -> Dict[str, Any]:
    """Replace sensitive values before writing them to the log."""
    clean: Dict[str, Any] = {}
    for key, value in details.items():
        if any(token in str(key).lower() for token in SECRET_KEYS):
            clean[key] = t("msg.audit.redacted")
        elif isinstance(value, dict):
            clean[key] = _redact(value)
        else:
            clean[key] = value
    return clean
