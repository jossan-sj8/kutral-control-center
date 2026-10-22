"""Real implementation of the `Storage` port, on BeeGFS.

It is the step that the inherited flow did with `ansible.builtin.user` (to create the
home) and the lab scripts. Here it is done directly, once, on the shared filesystem.

Three decisions that matter:

  - **Numeric `uid`/`gid` are used**, not names. The inherited flow ran `chown
    user:group` by name, and with a stale SSSD cache that either fails or assigns
    the wrong owner. The numbers come from the directory, which is the source of
    truth.
  - **`remove_home` refuses to delete outside the configured bases.** It is the most
    destructive operation in the project, and an `rm -rf` with the wrong path cannot
    be undone. If the path is not inside `beegfs_home` or `beegfs_labs`, it raises
    `StorageError` and touches nothing.
  - **A failed `chown` is not silenced**: it always warns, because a home left owned
    by `root` leaves the person unable to write in it.
"""

from __future__ import annotations

import os
import shutil
import tarfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..common import ui
from ..common.errors import StorageError
from ..common.i18n import t
from . import config as cfgmod

DEFAULT_HOME = "/mnt/beegfs/home"
DEFAULT_LABS = "/mnt/beegfs/labs"
#: Bash history: used by /etc/profile.d/history.sh on every login.
DEFAULT_HISTORY = "/mnt/beegfs/backup/history"
HOME_MODE = 0o750
LAB_MODE = 0o2770      # setgid: new files inherit the lab's group
HISTORY_MODE = 0o755


class Storage(object):
    """`Storage` port on top of the shared filesystem."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.home_base = cfgmod.path_for(config, "beegfs_home") or DEFAULT_HOME
        self.labs_base = cfgmod.path_for(config, "beegfs_labs") or DEFAULT_LABS
        self.history_base = cfgmod.path_for(config, "beegfs_history") or DEFAULT_HISTORY
        self.errors: List[str] = []
        self.actions: List[str] = []

    # -- paths ---------------------------------------------------------------

    def home(self, username: str) -> str:
        return os.path.join(self.home_base, username)

    def lab(self, group: str) -> str:
        return os.path.join(self.labs_base, group)

    def history(self, username: str) -> str:
        return os.path.join(self.history_base, username)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    # -- permissions ---------------------------------------------------------

    def _chown(self, path: str, uid: Optional[int], gid: Optional[int]) -> bool:
        """Assign the owner by number. If it cannot, it says so in detail."""
        if not hasattr(os, "chown"):
            return False
        try:
            os.chown(path, -1 if uid is None else uid, -1 if gid is None else gid)
            return True
        except OSError as exc:
            message = t("msg.storage.chown_failed", path=path, uid=uid, gid=gid, error=exc)
            self.errors.append(message)
            ui.warn(message)
            return False

    def _chmod(self, path: str, mode: int) -> bool:
        try:
            os.chmod(path, mode)
            return True
        except OSError as exc:
            message = t("msg.storage.chmod_failed", mode="{:o}".format(mode),
                        path=path, error=exc)
            self.errors.append(message)
            ui.warn(message)
            return False

    # -- safety guard --------------------------------------------------------

    def _assert_inside_bases(self, path: str) -> None:
        """It refuses to operate outside the configured shared directories."""
        target = os.path.realpath(path)
        allowed = [os.path.realpath(base)
                   for base in (self.home_base, self.labs_base, self.history_base)]
        if not any(target == base or target.startswith(base + os.sep) for base in allowed):
            raise StorageError(t("msg.storage.outside_bases", path=path,
                                 home=self.home_base, labs=self.labs_base))

    # -- creation ------------------------------------------------------------

    def ensure_home(self, username: str, uid: int, gid: int) -> str:
        """Create the home if missing, and set its owner and permissions."""
        path = self.home(username)
        os.makedirs(path, exist_ok=True)
        self._chown(path, uid, gid)
        self._chmod(path, HOME_MODE)
        self.actions.append("home {}".format(path))
        return path

    def ensure_lab(self, group: str, gid: int, mode: int = LAB_MODE) -> str:
        """Create the lab folder with setgid.

        The setgid (2770) is what makes files created by any member carry the lab's
        group instead of their primary group. Without it, collaborative work breaks
        file by file.
        """
        path = self.lab(group)
        os.makedirs(path, exist_ok=True)
        self._chown(path, None, gid)
        self._chmod(path, mode)
        self.actions.append("lab {}".format(path))
        return path

    def ensure_group_link(self, username: str, group: str, uid: int, gid: int) -> str:
        """Symbolic link to the lab, inside the home.

        On the cluster `/etc/profile.d/labs_symlink.sh` also does this on every login,
        so if it already exists it is left alone: recreating it could step on a link
        the system already manages.
        """
        link = os.path.join(self.home(username), group)
        if not os.path.lexists(link):
            os.makedirs(self.home(username), exist_ok=True)
            os.symlink(self.lab(group), link)
            if hasattr(os, "lchown"):
                try:
                    os.lchown(link, uid, gid)
                except OSError:
                    pass
        self.actions.append(t("msg.storage.action.link", path=link))
        return link

    def ensure_history(self, username: str, uid: int, gid: int) -> str:
        """Create the bash history folder and fix the owner if it was left old.

        The folder is named after the **user**, not their uid: if the account is
        deleted and created again with the same name, the folder survives with the
        previous owner and the login fails with "Permission denied" when writing
        `history_<host>`. That is why the owner is fixed —of the folder and of the
        files already inside it— besides creating it when missing.
        """
        path = self.history(username)
        self._assert_inside_bases(path)
        os.makedirs(path, exist_ok=True)
        if hasattr(os, "chown"):
            self._chown(path, uid, gid)
            for name in os.listdir(path):
                child = os.path.join(path, name)
                if os.path.isfile(child):
                    self._chown(child, uid, gid)
        self._chmod(path, HISTORY_MODE)
        self.actions.append(t("msg.storage.action.history", path=path))
        return path

    def move_history(self, old_username: str, new_username: str, uid: int, gid: int) -> str:
        """Move the bash history folder when the account is renamed.

        It always moves: the folder carries the user's name, not their uid, so leaving
        it under the old name leaves an orphan behind and wipes the person's history.
        If a folder with the new name already exists (left over from a previous
        account), it is not overwritten: it warns and fixes the owner of the one that
        exists.
        """
        source = self.history(old_username)
        target = self.history(new_username)
        self._assert_inside_bases(source)
        self._assert_inside_bases(target)
        if os.path.isdir(source) and not os.path.exists(target):
            try:
                os.rename(source, target)
            except OSError as exc:
                ui.warn(t("msg.storage.history_move_failed", origin=source,
                          destination=target, error=exc))
        elif os.path.isdir(source) and os.path.exists(target):
            ui.warn(t("msg.storage.history_exists", destination=target,
                      origin=source))
        if os.path.isdir(target):
            self._chown(target, uid, gid)
            for name in os.listdir(target):
                child = os.path.join(target, name)
                if os.path.isfile(child):
                    self._chown(child, uid, gid)
        self.actions.append(t("msg.storage.action.history_moved", origin=source,
                              destination=target))
        return target

    def move_home(self, old_username: str, new_username: str, uid: int, gid: int) -> str:
        """Rename the home when the username changes."""
        source = self.home(old_username)
        target = self.home(new_username)
        if os.path.exists(source):
            if os.path.exists(target):
                raise StorageError(t("msg.storage.home_exists", path=target))
            os.rename(source, target)
        else:
            os.makedirs(target, exist_ok=True)
        self._chown(target, uid, gid)
        self._chmod(target, HOME_MODE)
        self.actions.append("move {} -> {}".format(source, target))
        return target

    # -- archiving and deletion ----------------------------------------------

    def archive_home(self, username: str, home: str) -> str:
        """Archive the home into a tar.gz before deleting it."""
        self._assert_inside_bases(home)
        folder = os.path.join(self.home_base, "deleted_archives")
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = os.path.join(folder, "{}-{}.tar.gz".format(username, stamp))
        with tarfile.open(target, "w:gz") as bundle:
            if os.path.exists(home):
                bundle.add(home, arcname=username)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        self.actions.append("archive {} -> {}".format(home, target))
        return target

    def remove_home(self, home: str) -> None:
        """Delete a directory tree, with a path guard.

        It refuses if the path is not inside the configured bases, or if it is exactly
        one of them: it is the only irreversible operation in the project.
        """
        self._assert_inside_bases(home)
        target = os.path.realpath(home)
        for base in (self.home_base, self.labs_base):
            if target == os.path.realpath(base):
                raise StorageError(t("msg.storage.never_delete_base", path=home))
        if os.path.isdir(target) and not os.path.islink(target):
            shutil.rmtree(target)
        elif os.path.lexists(target):
            os.unlink(target)
        self.actions.append("remove {}".format(target))

    # -- diagnostics ---------------------------------------------------------

    def describe(self) -> Dict[str, Any]:
        return {"home_base": self.home_base, "labs_base": self.labs_base,
                "history_base": self.history_base,
                "chown_available": hasattr(os, "chown"),
                "errors": list(self.errors), "actions": list(self.actions)}
