"""Real implementation of the `SlurmAdmin` port, on top of `sacctmgr`.

Every call uses `subprocess` with a list of arguments —never `shell=True`— and `-i`
(non-interactive), so that they do not sit waiting for a confirmation nobody will type.

Where each command comes from, because inventing it is not the same as inheriting it:

    create user name=X DefaultAccount=Y   <- it is in add_users.sh
    remove user name=X                    <- it is in user_mgmt.py from V1
    add account account=X description=... <- it is in the group flow's note

The ones that do **not** come from any inherited script are marked `VERIFICAR` and are
precisely the ones to confirm on the first canary run.

About `available`: if `sacctmgr` is not on the host, the adapter exists but declares
itself unavailable. The CLI uses that to **refuse**, instead of running an operation
that is missing half of itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..common import ui
from ..common.errors import SlurmError
from ..common.i18n import t
from . import config as cfgmod

#: Runner signature: it receives the list of arguments and returns (code, stdout, stderr).
Runner = Callable[[List[str]], Tuple[int, str, str]]


def run_command(args: List[str], timeout: int = 60) -> Tuple[int, str, str]:
    """Run a command and return (code, output, error). It never raises."""
    try:
        completado = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return completado.returncode, completado.stdout or "", completado.stderr or ""
    except FileNotFoundError:
        return 127, "", t("msg.run.binary_missing", name=args[0])
    except subprocess.TimeoutExpired:
        return 124, "", t("msg.run.timeout", seconds=timeout)


class SlurmAdmin(object):
    """`SlurmAdmin` port on top of `sacctmgr`."""

    def __init__(self, config: Dict[str, Any], runner: Optional[Runner] = None,
                 binary: str = "sacctmgr", available: Optional[bool] = None) -> None:
        self.config = config
        self.binary = binary
        self.runner = runner or run_command
        self._available = available
        self.commands: List[List[str]] = []      # history of what was executed

    # -- diagnostics ----------------------------------------------------------

    @property
    def available(self) -> bool:
        if self._available is not None:
            return self._available
        return shutil.which(self.binary) is not None

    def _run(self, args: List[str], tolerate_error: bool = False) -> Tuple[int, str, str]:
        full_command = [self.binary] + args
        self.commands.append(full_command)
        code, output, error = self.runner(full_command)
        if code != 0 and not tolerate_error:
            raise SlurmError(t("msg.slurm.command_failed",
                               command=" ".join(full_command[1:]),
                               error=(error or output).strip()[:300]))
        return code, output, error

    @staticmethod
    def _lines(output: str) -> List[str]:
        return [line.strip() for line in output.splitlines() if line.strip()]

    # -- accounts -------------------------------------------------------------

    def account_exists(self, account: str) -> bool:
        _, output, _ = self._run(
            ["-n", "-P", "show", "account", account, "format=Account"],
            tolerate_error=True)
        return bool(self._lines(output))

    def create_account(self, account: str, description: str = "",
                       organization: str = "") -> bool:
        args = ["-i", "add", "account", "account={}".format(account)]
        if description:
            args.append("description={}".format(description))
        if organization:
            args.append("organization={}".format(organization))
        self._run(args)
        return True

    def delete_account(self, account: str) -> bool:
        # VERIFICAR on the canary: if this Slurm version prefers the form
        # `delete account where account=X`, it is a one-line change.
        code, _, error = self._run(["-i", "delete", "account", account],
                                  tolerate_error=True)
        if code != 0:
            ui.warn(t("msg.slurm.account_delete_failed", account=account,
                      error=(error or "").strip()[:160]))
            return False
        return True

    # -- users ----------------------------------------------------------------

    def user_exists(self, username: str) -> bool:
        _, output, _ = self._run(
            ["-n", "-P", "show", "user", username, "format=User"], tolerate_error=True)
        # Careful with `-P`: fields are separated by `|`, so a single column arrives as
        # "iprado|". Comparing against the bare name would always give False, and the
        # "user already exists" path (add and set the account) would never be taken:
        # `add user` would fail with "already exists" and abort the operation.
        for line in self._lines(output):
            if line.split("|")[0].strip() == username:
                return True
        return False

    def associations(self, username: str) -> List[str]:
        """Accounts the user is associated with, without repeats."""
        _, output, _ = self._run(
            ["-n", "-P", "show", "assoc", "user={}".format(username), "format=Account"],
            tolerate_error=True)
        accounts: List[str] = []
        for line in self._lines(output):
            account = line.split("|")[0].strip() if "|" in line else line.strip()
            if account and account not in accounts:
                accounts.append(account)
        return accounts

    def register_user(self, username: str, account: str) -> bool:
        """Associate the user with the account and leave it as the default one.

        Two steps, because `add user` with a user that already exists fails: first the
        association is added (tolerating that it is already there) and then
        `DefaultAccount` is set, which on this cluster means "their group".
        """
        # The account has to exist before associating: a group can be in the directory
        # and **not** be a Slurm account (`gprueba2`, `pmd2025`…). Without this, `add
        # user` fails and the error only shows up when setting `DefaultAccount` —with
        # the directory already modified and, on a reactivation, **before** sending the
        # person the mail, who is left with no credentials and no warning.
        if not self.account_exists(account):
            self.create_account(account)
        if self.user_exists(username):
            self._run(["-i", "add", "user", "name={}".format(username),
                       "account={}".format(account)], tolerate_error=True)
            # VERIFICAR on the canary: the way to change the default account.
            self._run(["-i", "update", "user", "name={}".format(username),
                       "set", "DefaultAccount={}".format(account)], tolerate_error=True)
        else:
            self._run(["-i", "add", "user", "name={}".format(username),
                       "DefaultAccount={}".format(account)])
        return True

    def remove_user(self, username: str) -> bool:
        code, _, error = self._run(["-i", "remove", "user", "name={}".format(username)],
                                  tolerate_error=True)
        if code != 0:
            ui.warn(t("msg.slurm.user_remove_failed", username=username,
                      error=(error or "").strip()[:160]))
            return False
        return True

    # -- association backup ---------------------------------------------------

    def _backup_dir(self) -> str:
        base = cfgmod.path_for(self.config, "backups_dir") or "backups"
        path = os.path.join(base, "slurm")
        os.makedirs(path, exist_ok=True)
        return path

    def save_associations(self, username: str) -> Optional[str]:
        """Save the user's accounts before removing them.

        It is what makes it possible to reactivate without losing labs: a user of two
        groups gets both back, not just the default account.
        """
        accounts = self.associations(username)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(self._backup_dir(), "{}-{}.json".format(username, stamp))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"username": username, "accounts": accounts, "ts": stamp},
                      handle, indent=2, ensure_ascii=False)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    def load_saved_associations(self, username: str) -> List[str]:
        """Accounts from the most recent backup, or an empty list."""
        folder = self._backup_dir()
        try:
            candidates = sorted((name for name in os.listdir(folder)
                                 if name.startswith("{}-".format(username))
                                 and name.endswith(".json")), reverse=True)
        except OSError:
            return []
        if not candidates:
            return []
        try:
            with open(os.path.join(folder, candidates[0]), "r", encoding="utf-8") as handle:
                return list(json.load(handle).get("accounts") or [])
        except (OSError, ValueError):
            return []

    def restore_associations(self, username: str, fallback_account: str) -> List[str]:
        """Re-associate the user from the backup; if there is none, use `fallback`.

        Falling back to the default account **warns**: silently, the person goes back to
        `hpc-default` and everybody believes they recovered their lab.
        """
        saved = self.load_saved_associations(username)
        if not saved:
            ui.warn(t("msg.slurm.no_backup", username=username,
                      account=fallback_account))
        accounts = saved or [fallback_account]
        for account in accounts:
            self.register_user(username, account)
        return accounts

    def describe(self) -> Dict[str, Any]:
        return {"binary": self.binary, "available": self.available,
                "commands_run": len(self.commands)}
