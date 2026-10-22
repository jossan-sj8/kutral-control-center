"""Execution of the configured external commands (hooks).

They are the inherited steps that are neither LDAP nor Slurm: the Nextcloud
storage (`agrega_storage_user.sh`) and the home's SSH key generation. They are kept
as configurable commands instead of being reimplemented, because they belong to
another repo and not everything they do is known.

Two precautions the inherited flow did not take:

1. **The password does not travel on the command line.** It is written into a
   temporary file with 600 permissions, the *path* is passed as `{password_file}`
   and the file is deleted when done. It used to leave `tmpN.pass.txt` files with
   the password in the clear in the scripts directory, and the LDAP Manager
   password travelled in `ldapmodify -w`, visible in `ps`.
2. **Values are quoted.** `{username}` and friends are substituted with
   `shlex.quote`, so a value with spaces or quotes cannot change the command that
   runs.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

from ..common.i18n import t
from . import config as cfgmod

#: Sensitive keys that are **not** passed to the command nor to the context file.
SECRET_KEYS = ("password", "temp_pass", "userpassword")

HOOK_SECTIONS = ("after_create", "after_delete", "after_group_create")


class ShellHooks(object):
    """Real implementation of the `Hooks` port."""

    def __init__(self, config: Dict[str, Any], timeout: int = 120) -> None:
        self.config = config
        self.timeout = timeout

    def commands_for(self, name: str) -> List[str]:
        return list(cfgmod.get(self.config, "hooks.{}".format(name), []) or [])

    def run(self, name: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run every command of `name` and return one result per command."""
        templates = self.commands_for(name)
        if not templates:
            return []

        secret_path = None
        values: Dict[str, Any] = {}
        for key, value in context.items():
            if str(key).lower() in SECRET_KEYS:
                continue
            if key == "config":
                continue
            values[key] = shlex.quote("" if value is None else str(value))
        password = context.get("password") or context.get("temp_pass")
        if password:
            secret_path = _write_secret(password)
            values["password_file"] = shlex.quote(secret_path)

        results: List[Dict[str, Any]] = []
        try:
            for template in templates:
                try:
                    command = template.format(**values)
                except KeyError as exc:
                    results.append({"command": template, "ok": False,
                                    "error": t("msg.hooks.missing_context",
                                               name=exc.args[0])})
                    continue
                try:
                    completed = subprocess.run(command, shell=True, capture_output=True,
                                               text=True, timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    results.append({"command": command, "ok": False,
                                    "error": t("msg.hooks.timeout",
                                               seconds=self.timeout)})
                    continue
                results.append({
                    "command": command,
                    "ok": completed.returncode == 0,
                    "returncode": completed.returncode,
                    "stderr": (completed.stderr or "").strip()[-500:],
                })
        finally:
            _remove_secret(secret_path)
        return results

    def describe(self) -> Dict[str, List[str]]:
        return {section: self.commands_for(section) for section in HOOK_SECTIONS}


def _write_secret(value: str) -> str:
    """Write the password into a temporary file with 600 permissions."""
    handle, path = tempfile.mkstemp(prefix="kutral-pass-", suffix=".txt")
    try:
        os.write(handle, value.encode("utf-8"))
    finally:
        os.close(handle)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - on Windows it does not apply the same way
        pass
    return path


def _remove_secret(path: Any) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except OSError as exc:  # pragma: no cover
        print("[-] " + t("msg.hooks.temp_delete_failed", path=path, error=exc),
              file=sys.stderr)
