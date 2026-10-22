"""Real implementation of the `Identity` port: SSSD cache and name resolution.

Two things that look the same and are not:

  - **`sss_cache`** clears the SSSD cache so the system sees a directory change at
    once. Without it, a freshly created user may take a while to log in, and a
    deleted one may still be resolved from the cache.
  - **`getent passwd`** resolves the user the way the system does, that is, **by
    consulting `nsswitch`**. And there lies the cluster's problem: with
    `passwd: files sss`, the local copy in `/etc/passwd` wins. That is why deletion
    required cleaning `.154` and `.158` by hand.

That is why `local_account_exists` **does not use `getent`**: it reads
`/etc/passwd` directly. With `getent` it would answer "exists" both for a local
account and for an LDAP one, and it would not tell the case that matters apart.

The runner and the path of `/etc/passwd` are injectable, so this can be tested
without a cluster and without root.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..common import ui
from ..common.i18n import t
from . import config as cfgmod

#: Runner signature: list of arguments -> (code, stdout, stderr).
Runner = Callable[[List[str]], Tuple[int, str, str]]


def run_command(args: List[str], timeout: int = 60) -> Tuple[int, str, str]:
    try:
        completado = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return completado.returncode, completado.stdout or "", completado.stderr or ""
    except FileNotFoundError:
        return 127, "", t("msg.run.binary_missing", name=args[0])
    except subprocess.TimeoutExpired:
        return 124, "", t("msg.run.timeout", seconds=timeout)


class Identity(object):
    """`Identity` port on top of `sss_cache`, `getent` and `/etc/passwd`."""

    def __init__(self, config: Dict[str, Any], runner: Optional[Runner] = None,
                 passwd_path: str = "/etc/passwd", binary_sss: str = "sss_cache",
                 binary_getent: str = "getent") -> None:
        self.config = config
        self.runner = runner or run_command
        self.passwd_path = passwd_path
        self.binary_sss = binary_sss
        self.binary_getent = binary_getent
        self.commands: List[List[str]] = []

    # -- cache refresh --------------------------------------------------------

    @property
    def sss_available(self) -> bool:
        return shutil.which(self.binary_sss) is not None

    def _refresh(self, args: List[str]) -> bool:
        completo = [self.binary_sss] + args
        self.commands.append(completo)
        codigo, _, error = self.runner(completo)
        if codigo != 0:
            # `sss_cache` exits with an error and says "No hay objetos en el cache…"
            # when the object is not cached yet: there is nothing stale to purge, so
            # it is not a failure. It showed up on every change of a user's primary
            # group when nobody had resolved the new group yet, and it dirtied the
            # output with something that looked like a problem. Both texts are matched
            # because the message comes in the host's locale.
            if any(text in (error or "").lower() for text in
                   ("no hay objetos en el cache", "no entries in the cache")):
                return True
            # It does not abort: a failed refresh leaves the cache old, it does not
            # break the change. But the operator has to know, because it explains why
            # "the user does not see the change yet".
            ui.warn(t("msg.identity.refresh_failed", command=" ".join(completo[1:]),
                      error=(error or "").strip()[:160]))
            return False
        return True

    def refresh_all(self) -> bool:
        """Purge the whole cache (`sss_cache -E`), like the inherited flow."""
        return self._refresh(["-E"])

    def refresh_group(self, group: str) -> bool:
        return self._refresh(["-g", group])

    def refresh_user(self, username: str) -> bool:
        return self._refresh(["-u", username])

    # -- resolution -----------------------------------------------------------

    def resolve(self, username: str) -> Optional[Dict[str, Any]]:
        """Resolve like `getent passwd`, including the local path."""
        completo = [self.binary_getent, "passwd", username]
        self.commands.append(completo)
        codigo, salida, _ = self.runner(completo)
        if codigo != 0 or not salida.strip():
            return None
        resuelto = self._parse_passwd_line(salida.strip().splitlines()[0])
        if resuelto is not None and self.local_account_exists(username):
            resuelto["source"] = "local"
        return resuelto

    @staticmethod
    def _parse_passwd_line(linea: str) -> Optional[Dict[str, Any]]:
        campos = linea.split(":")
        if len(campos) < 7:
            return None
        return {"username": campos[0], "password": campos[1], "uid": campos[2],
                "gid": campos[3], "gecos": campos[4], "home": campos[5],
                "shell": campos[6], "source": "nss"}

    def local_account_exists(self, username: str) -> bool:
        """True if the account is in the host's `/etc/passwd` **as a local line**.

        The file is read and not `getent` on purpose: `getent` would also resolve an
        LDAP user, and the goal is to tell "exists locally" from "SSSD resolves it".
        """
        try:
            with open(self.passwd_path, "r", encoding="utf-8", errors="replace") as manejador:
                for linea in manejador:
                    if linea.startswith("{}:".format(username)):
                        return True
        except OSError:
            return False
        return False

    def local_accounts(self) -> List[str]:
        """Local accounts with a person's uid (1000 <= uid < 60000).

        It is the list currently mirrored on `.154` and `.158`, and the one to check
        against the directory to find orphans.
        """
        nombres: List[str] = []
        try:
            with open(self.passwd_path, "r", encoding="utf-8", errors="replace") as manejador:
                for linea in manejador:
                    campos = linea.split(":")
                    if len(campos) < 4:
                        continue
                    try:
                        uid = int(campos[2])
                    except ValueError:
                        continue
                    if 1000 <= uid < 60000:
                        nombres.append(campos[0])
        except OSError:
            return []
        return nombres

    def describe(self) -> Dict[str, Any]:
        existe = os.path.exists(self.passwd_path)
        return {"sss_cache": self.binary_sss, "sss_available": self.sss_available,
                "getent": self.binary_getent, "passwd_path": self.passwd_path,
                "local_accounts": len(self.local_accounts()) if existe else None,
                "commands_run": len(self.commands)}
