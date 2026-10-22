"""Test doubles for Slurm, mail, storage and identity.

`fake_directory.py` covers LDAP. This file covers the rest of the outside world, and
with that the whole control center runs **with no cluster, no network and no VPN**:
rehearsal mode (`--config config.lab.yaml`) uses exactly these objects.

Three decisions that are not accidental:

  - **`SandboxStorage` creates real directories.** The tree is real and can be opened
    in the file explorer; what is not applied is ownership, because on Windows
    `os.chown` does not exist. Instead it is recorded in a JSON, so it can be verified
    *which* uid/gid/mode would have been applied — which is what matters when the goal
    is to test the logic, not the filesystem.
  - **`FileMailer` writes the mails as `.eml` files.** They open in the browser or the
    mail client, so the HTML is really reviewed instead of assumed.
  - **`FakeIdentity` models the cluster's central problem**: `nsswitch` with `files`
    before `sss`. A user with a local account **is still resolved even though it no
    longer exists in LDAP**. That is what used to force deleting on `.154` and `.158`
    by hand, and it is what makes it possible to test the deletion check without
    touching the cluster.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
from typing import Any, Dict, List, Optional, Set

from ..core.audit import NullAuditor


# ---------------------------------------------------------------------------
# Slurm
# ---------------------------------------------------------------------------

class FakeSlurm(object):
    """In-memory implementation of the `SlurmAdmin` port."""

    def __init__(self, accounts: Optional[List[str]] = None,
                 users: Optional[Dict[str, List[str]]] = None,
                 available: bool = True) -> None:
        self.available = available
        self.accounts: Set[str] = set(accounts or [])
        self.users: Dict[str, List[str]] = {k: list(v) for k, v in (users or {}).items()}
        self.saved: Dict[str, List[str]] = {}
        self.calls: List[tuple] = []

    def account_exists(self, account: str) -> bool:
        return account in self.accounts

    def create_account(self, account: str, description: str = "", organization: str = "") -> bool:
        self.calls.append(("create_account", account))
        self.accounts.add(account)
        return True

    def delete_account(self, account: str) -> bool:
        self.calls.append(("delete_account", account))
        existed = account in self.accounts
        self.accounts.discard(account)
        return existed

    def user_exists(self, username: str) -> bool:
        return username in self.users

    def associations(self, username: str) -> List[str]:
        return list(self.users.get(username, []))

    def register_user(self, username: str, account: str) -> bool:
        self.calls.append(("register_user", username, account))
        self.accounts.add(account)
        current = self.users.setdefault(username, [])
        if account not in current:
            current.insert(0, account)
        return True

    def remove_user(self, username: str) -> bool:
        self.calls.append(("remove_user", username))
        return self.users.pop(username, None) is not None

    def save_associations(self, username: str) -> Optional[str]:
        """Back up the associations before removing them.

        It is what prevents losing the accounts of a user who belongs to several labs
        when they are deactivated and reactivated.
        """
        self.calls.append(("save_associations", username))
        self.saved[username] = list(self.users.get(username, []))
        return "sandbox/slurm/{}-associations.json".format(username)

    def restore_associations(self, username: str, fallback_account: str) -> List[str]:
        self.calls.append(("restore_associations", username))
        accounts = self.saved.get(username) or [fallback_account]
        self.users[username] = list(accounts)
        return list(accounts)


# ---------------------------------------------------------------------------
# Storage (BeeGFS simulated in a real sandbox)
# ---------------------------------------------------------------------------

class SandboxStorage(object):
    """Implementation of the `Storage` port with real directories in a sandbox."""

    def __init__(self, config: Dict[str, Any], root: Optional[str] = None) -> None:
        paths = config.get("paths", {}) or {}
        self.root = root or config.get("_base_dir") or os.getcwd()
        self.home_base = self._resolve(paths.get("beegfs_home", "sandbox/mnt/beegfs/home"))
        self.labs_base = self._resolve(paths.get("beegfs_labs", "sandbox/mnt/beegfs/labs"))
        self.history_base = self._resolve(
            paths.get("beegfs_history", "sandbox/mnt/beegfs/backup/history"))
        self.ownership: Dict[str, Dict[str, Any]] = {}
        self.calls: List[tuple] = []

    def _resolve(self, value: str) -> str:
        if os.path.isabs(value):
            return value
        return os.path.normpath(os.path.join(self.root, value))

    def _record(self, path: str, uid: Optional[int] = None, gid: Optional[int] = None,
                mode: Optional[int] = None) -> None:
        """Record the ownership that would have been applied.

        On Linux this would be `os.chown` + `os.chmod`; here it is recorded, which is the
        only thing verifiable from Windows and the only thing that matters to test the
        logic (that a lab gets 2770 with setgid, for instance).
        """
        self.ownership[path] = {"uid": uid, "gid": gid, "mode": mode}
        sidecar = os.path.join(self.root, "sandbox", "ownership.json")
        os.makedirs(os.path.dirname(sidecar), exist_ok=True)
        with open(sidecar, "w", encoding="utf-8") as handle:
            json.dump(self.ownership, handle, indent=2, sort_keys=True)

    def ownership_of(self, path: str) -> Dict[str, Any]:
        return self.ownership.get(path, {})

    def home(self, username: str) -> str:
        return os.path.join(self.home_base, username)

    def lab(self, group: str) -> str:
        return os.path.join(self.labs_base, group)

    def history(self, username: str) -> str:
        return os.path.join(self.history_base, username)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def ensure_home(self, username: str, uid: int, gid: int) -> str:
        path = self.home(username)
        os.makedirs(path, exist_ok=True)
        self._record(path, uid, gid, 0o750)
        self.calls.append(("ensure_home", path))
        return path

    def ensure_lab(self, group: str, gid: int, mode: int = 0o2770) -> str:
        path = self.lab(group)
        os.makedirs(path, exist_ok=True)
        self._record(path, -1, gid, mode)
        self.calls.append(("ensure_lab", path))
        return path

    def ensure_history(self, username: str, uid: int, gid: int) -> str:
        """Create the history folder and record the owner that would be applied.

        It reproduces the real case that motivated the method: the folder already existed
        owned by a deleted account (same name, old uid) and the owner is fixed instead of
        leaving the login broken.
        """
        path = self.history(username)
        os.makedirs(path, exist_ok=True)
        self._record(path, uid, gid, 0o755)
        self.calls.append(("ensure_history", path))
        return path

    def ensure_group_link(self, username: str, group: str, uid: int, gid: int) -> str:
        """Symlink to the lab directory, inside the home.

        On Windows creating symlinks requires privileges, so if it fails a marker file is
        left with the target. The link's destination stays just as verifiable.
        """
        hogar = self.home(username)
        os.makedirs(hogar, exist_ok=True)
        enlace = os.path.join(hogar, group)
        try:
            if not os.path.islink(enlace) and not os.path.exists(enlace):
                os.symlink(self.lab(group), enlace)
        except (OSError, NotImplementedError, AttributeError):
            with open(enlace + ".symlink", "w", encoding="utf-8") as handle:
                handle.write(self.lab(group))
        self._record(enlace, uid, gid, None)
        self.calls.append(("ensure_group_link", enlace))
        return enlace

    def move_history(self, old_username: str, new_username: str, uid: int, gid: int) -> str:
        """Move the history folder on rename (and record the new owner)."""
        source = self.history(old_username)
        target = self.history(new_username)
        if os.path.isdir(source) and not os.path.exists(target):
            os.rename(source, target)
        os.makedirs(target, exist_ok=True)
        self._record(target, uid, gid, 0o755)
        self.calls.append(("move_history", source, target))
        return target

    def move_home(self, old_username: str, new_username: str, uid: int, gid: int) -> str:
        source = self.home(old_username)
        target = self.home(new_username)
        if os.path.exists(source):
            os.rename(source, target)
        self._record(target, uid, gid, 0o750)
        self.ownership.pop(source, None)
        self.calls.append(("move_home", source, target))
        return target

    def archive_home(self, username: str, home: str) -> str:
        """Archive the home into a real tar.gz, inside the sandbox."""
        target_dir = os.path.join(self.home_base, "deleted_archives")
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, "{}.tar.gz".format(username))
        if os.path.exists(home):
            with tarfile.open(target, "w:gz") as tar:
                tar.add(home, arcname=username)
        else:
            with tarfile.open(target, "w:gz"):
                pass
        self.calls.append(("archive_home", home, target))
        return target

    def remove_home(self, home: str) -> None:
        if os.path.isdir(home):
            shutil.rmtree(home, ignore_errors=True)
        self.ownership.pop(home, None)
        self.calls.append(("remove_home", home))


# ---------------------------------------------------------------------------
# Correo
# ---------------------------------------------------------------------------

class FileMailer(object):
    """Implementation of the `Mailer` port that writes `.eml` files."""

    def __init__(self, config: Dict[str, Any], outdir: Optional[str] = None) -> None:
        base = config.get("_base_dir") or os.getcwd()
        paths = config.get("paths", {}) or {}
        self.outdir = outdir or os.path.normpath(
            os.path.join(base, paths.get("mail_dir", "sandbox/mail")))
        self.calls: List[Dict[str, Any]] = []

    def send(self, kind: str, to: str, **context: Any) -> bool:
        # The kind is validated just like in the real mailer. A double more permissive
        # than the real one lets bugs through in silence: on 2026-10-15 the reset mail
        # came out "ok" in the tests and failed in production with "Unknown mail kind".
        from ..core.smtp_mailer import normalize_kind

        normalize_kind(kind)
        os.makedirs(self.outdir, exist_ok=True)
        index = len(self.calls) + 1
        safe_to = to.replace("@", "_at_").replace("/", "_")
        path = os.path.join(self.outdir, "{:03d}-{}-{}.eml".format(index, kind, safe_to))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("To: {}\n".format(to))
            handle.write("Subject: [sandbox] {}\n".format(kind))
            handle.write("X-Environment: {}\n\n".format(
                (context.get("config") or {}).get("environment", "lab")))
            for key in sorted(context):
                if key == "config":
                    continue
                handle.write("{}: {}\n".format(key, context[key]))
        self.calls.append({"kind": kind, "to": to, "path": path, "context": context})
        return True

    def kinds(self) -> List[str]:
        return [item["kind"] for item in self.calls]

    def last(self) -> Optional[Dict[str, Any]]:
        return self.calls[-1] if self.calls else None


# ---------------------------------------------------------------------------
# Identity (SSSD + local accounts)
# ---------------------------------------------------------------------------

class RecordingHooks(object):
    """Implementation of the `Hooks` port that records instead of executing.

    The real commands belong to another repo and create Nextcloud storage and SSH keys:
    none of that can or should run in a test. What is tested is that the domain invokes
    them at the right moment and with the full context.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 available: Optional[Dict[str, List[str]]] = None) -> None:
        self.config = config or {}
        self.available = available or {}
        self.calls: List[Dict[str, Any]] = []

    def run(self, name: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.calls.append({"name": name, "context": dict(context)})
        comandos = self.available.get(name) or (self.config.get("hooks", {}) or {}).get(name) or []
        return [{"command": template, "ok": True, "returncode": 0, "stderr": ""}
                for template in comandos]

    def names(self) -> List[str]:
        return [call["name"] for call in self.calls]


class FakeIdentity(object):
    """Implementation of the `Identity` port that reproduces `files` before `sss`."""

    def __init__(self, directory: Any, local_accounts: Optional[Set[str]] = None) -> None:
        self.directory = directory
        self.local_accounts: Set[str] = set(local_accounts or [])
        self.calls: List[tuple] = []

    def refresh_all(self) -> bool:
        self.calls.append(("refresh_all",))
        return True

    def refresh_group(self, group: str) -> bool:
        self.calls.append(("refresh_group", group))
        return True

    def refresh_user(self, username: str) -> bool:
        self.calls.append(("refresh_user", username))
        return True

    def local_account_exists(self, username: str) -> bool:
        return username in self.local_accounts

    def forget_local(self, username: str) -> None:
        """Simulate cleaning a host's local account (the `userdel` done by hand today)."""
        self.local_accounts.discard(username)

    def resolve(self, username: str) -> Optional[Dict[str, Any]]:
        """Resolve the way the system does: `files` first, then `sss`.

        That is why a local account **stays alive for the system** even though its LDAP
        entry has been deleted. It is the reason deletion used to require two steps on
        `.154` and `.158`.
        """
        if username in self.local_accounts:
            return {"uid": username, "source": "local"}
        if self.directory is not None and self.directory.get_user(username) is not None:
            return {"uid": username, "source": "ldap"}
        return None


# ---------------------------------------------------------------------------
# Ensamblado
# ---------------------------------------------------------------------------

def build_environment(config: Dict[str, Any], directory: Any = None,
                      local_accounts: Optional[Set[str]] = None,
                      slurm_accounts: Optional[List[str]] = None,
                      storage_root: Optional[str] = None,
                      mail_outdir: Optional[str] = None,
                      state_path: Optional[str] = None) -> Any:
    """Build a complete rehearsal `Environment`, with no cluster.

    It is the only point where the domain stops touching the real world: if something
    cannot be tested with this, it is because the domain is calling `subprocess` or
    `os.chown` outside the ports.
    """
    from ..core.ports import Environment
    from .fake_directory import FakeDirectory
    from .seed import build_seed

    if directory is None:
        # If there is saved state, it continues from there: it is what makes it possible
        # to chain CLI commands in rehearsal mode.
        if state_path and os.path.exists(state_path):
            directory = FakeDirectory.cargar_estado(config, state_path)
        else:
            directory = FakeDirectory(config, build_seed(config))

    return Environment(
        config=config,
        directory=directory,
        slurm=FakeSlurm(accounts=slurm_accounts or ["hpc-default"]),
        mailer=FileMailer(config, outdir=mail_outdir),
        storage=SandboxStorage(config, root=storage_root),
        identity=FakeIdentity(directory, local_accounts=local_accounts),
        auditor=NullAuditor(),
        hooks=RecordingHooks(config),
    )
