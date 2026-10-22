"""Ports: the contracts between the domain and the infrastructure.

This file is the piece that makes it possible to test everything without being on
the cluster. The domain (users/, groups/) declares here what it needs, and never
calls subprocess, os.chown or the network directly.

Every port has two implementations:
  - real: core/slurm_admin.py, core/smtp_mailer.py, core/storage.py, core/identity.py
  - fake: modules/testing/fake_services.py  (it records the calls, touches nothing)

The CLI builds an `Environment` and injects it. The tests build the same object with
the fake implementations, and that way they exercise 100% of the decision logic
—wizards, validations, sequence of steps, mail— with no cluster.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class SlurmAdmin(Protocol):
    """Slurm operations the user and group lifecycle needs."""

    @property
    def available(self) -> bool:
        """True if sacctmgr is present on this host."""

    def account_exists(self, account: str) -> bool: ...

    def create_account(self, account: str, description: str = "", organization: str = "") -> bool: ...

    def delete_account(self, account: str) -> bool: ...

    def user_exists(self, username: str) -> bool: ...

    def associations(self, username: str) -> List[str]:
        """Accounts the user is associated with."""

    def register_user(self, username: str, account: str) -> bool:
        """Associate the user with the account (DefaultAccount=account)."""

    def remove_user(self, username: str) -> bool:
        """Remove every association of the user."""

    def save_associations(self, username: str) -> Optional[str]:
        """Back up the associations before removing them. Returns the path."""

    def restore_associations(self, username: str, fallback_account: str) -> List[str]:
        """Re-associate the user from the backup. Returns the restored accounts."""


@runtime_checkable
class Directory(Protocol):
    """LDAP operations the domain needs.

    It returns dictionaries, not ldap3 objects: that way the domain (users/,
    groups/) never imports ldap3, and the fake implementation is interchangeable
    without any other part of the code noticing.
    """

    def get_user(self, uid: str) -> Optional[Dict[str, Any]]: ...

    def search_users(self, term: str) -> List[Dict[str, Any]]:
        """Exact uid, or a partial match on cn/mail/uid."""

    def list_users(self) -> List[Dict[str, Any]]: ...

    def user_exists(self, uid: str) -> bool: ...

    def create_user(self, attributes: Dict[str, Any]) -> str:
        """Create the account and return the resulting DN."""

    def get_group(self, name: str) -> Optional[Dict[str, Any]]: ...

    def list_groups(self) -> List[Dict[str, Any]]: ...

    def group_exists(self, name: str) -> bool: ...

    def memberships(self, username: str) -> List[str]:
        """Groups whose memberUid includes the user."""

    def add_member(self, group: str, username: str) -> bool:
        """Add the memberUid and return True **only if something changed**.

        Idempotence belongs to the adapter, not to the domain: the adapter is the
        one that can know whether the user was already a member without an extra
        read. That way, adding twice does not report a change that did not happen.
        """

    def remove_member(self, group: str, username: str) -> bool:
        """Remove the memberUid and return True **only if something changed**."""

    def create_group(self, name: str, gid: int, members: Optional[List[str]] = None) -> str: ...

    def update(self, dn: str, changes: Dict[str, Any]) -> None:
        """replace of complete attributes."""

    def add_values(self, dn: str, changes: Dict[str, Any]) -> None:
        """MODIFY_ADD: add values to a multi-valued attribute (e.g. memberUid)."""

    def remove_values(self, dn: str, changes: Dict[str, Any]) -> None:
        """MODIFY_DELETE: remove values from a multi-valued attribute."""

    def set_password(self, dn: str, password: str) -> None: ...

    def rename(self, dn: str, new_uid: str) -> str:
        """Rename the RDN (username change) and return the new DN."""

    def delete(self, dn: str) -> None: ...

    def next_uid(self) -> int: ...

    def retired_uids(self) -> List[int]:
        """Uids a deleted account already used, which must not be reused."""

    def retire_uid(self, uid: Any, username: Optional[str] = None) -> None:
        """Record a uid as retired, so that `next_uid` never returns it.

        The bash history folder and the orphan files in BeeGFS carry the
        **number**, not the name: reassigning it hands one person's files to
        another. It is called when deleting an account.
        """

    def next_gid(self) -> int: ...

    def user_dn(self, uid: str) -> str: ...

    def group_dn(self, name: str) -> str: ...

    def save_entry(self, dn: str, for_restore: bool = False) -> str:
        """Write an LDIF of the entry so it can be reverted. Returns the path.

        With `for_restore=True` it is written in the format `ldapadd` accepts to
        **recreate** a deleted entry; without it, in the one `ldapmodify` accepts to
        revert a change. They are two different formats, and deletion needs the
        first one: a `modify` LDIF cannot recreate what is no longer there.
        """


@runtime_checkable
class Mailer(Protocol):
    """Mail delivery. `kind` identifies the template."""

    def send(self, kind: str, to: str, **context: Any) -> bool: ...


@runtime_checkable
class Storage(Protocol):
    """Shared directories in BeeGFS (home, labs and bash history)."""

    def home(self, username: str) -> str: ...

    def lab(self, group: str) -> str: ...

    def exists(self, path: str) -> bool: ...

    def ensure_home(self, username: str, uid: int, gid: int) -> str: ...

    def ensure_lab(self, group: str, gid: int, mode: int = 0o2770) -> str: ...

    def ensure_group_link(self, username: str, group: str, uid: int, gid: int) -> str: ...

    def ensure_history(self, username: str, uid: int, gid: int) -> str:
        """Bash history folder: `/mnt/beegfs/backup/history/<username>`.

        `/etc/profile.d/history.sh` uses it on every login. Because the folder
        carries the user's **name** and not their uid, recreating a deleted account
        leaves it owned by the old user and the login fails with "Permission
        denied" when writing the history: that is why it also fixes the owner when
        it does not match.
        """

    def move_home(self, old_username: str, new_username: str, uid: int, gid: int) -> str: ...

    def move_history(self, old_username: str, new_username: str, uid: int, gid: int) -> str:
        """Move the bash history folder when the account is renamed.

        It moves **always**, even with `--keep-home`: the folder carries the user's
        name, so leaving it under the old name means the new login starts with an
        empty history and an orphan folder stays behind that nobody relates to that
        person again.
        """

    def archive_home(self, username: str, home: str) -> str:
        """Archive the home and return the path of the tar.gz."""

    def remove_home(self, home: str) -> None: ...


@runtime_checkable
class Identity(Protocol):
    """Identity cache (SSSD)."""

    def refresh_all(self) -> bool: ...

    def refresh_group(self, group: str) -> bool: ...

    def refresh_user(self, username: str) -> bool: ...

    def resolve(self, username: str) -> Optional[Dict[str, Any]]:
        """Resolve the user the way `getent passwd` would."""

    def local_account_exists(self, username: str) -> bool:
        """True if the user exists as a LOCAL account in /etc/passwd."""


@runtime_checkable
class Hooks(Protocol):
    """External commands fired at points of the lifecycle.

    It is what allows keeping the inherited steps that are neither LDAP nor Slurm:
    the Nextcloud storage (`agrega_storage_user.sh`) and the SSH key generation.
    They live in configuration (`hooks.after_create`, `hooks.after_delete`) and not
    in the code, so they can be turned off without touching the domain.

    The password is **never** passed on the command line: it is written into a
    temporary file with 600 permissions and deleted when done. That is what
    replaces the `tmpN.pass.txt` files that were left lying around in the scripts
    directory.
    """

    def run(self, name: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run the commands of `name`. Returns one result per command."""


@runtime_checkable
class Auditor(Protocol):
    """Audit record: who did what, when, and with what result."""

    def record(self, action: str, target: str, details: Optional[Dict[str, Any]] = None,
               result: str = "ok", dry_run: bool = False) -> None: ...


class Environment(object):
    """Dependency container the domain receives injected.

    It is the only point through which the domain touches the outside world.
    Switching prod for tests is switching this object.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        directory: Any,
        slurm: Optional[SlurmAdmin] = None,
        mailer: Optional[Mailer] = None,
        storage: Optional[Storage] = None,
        identity: Optional[Identity] = None,
        auditor: Optional[Auditor] = None,
        hooks: Optional[Hooks] = None,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.directory = directory
        self.slurm = slurm
        self.mailer = mailer
        self.storage = storage
        self.identity = identity
        self.auditor = auditor
        self.hooks = hooks
        self.dry_run = dry_run

    @property
    def mail_policy(self) -> str:
        """ask | always | never, from the configuration."""
        return str(self.config.get("cluster", {}).get("send_mail", "ask"))

    def __repr__(self) -> str:  # pragma: no cover
        return "Environment(environment={!r}, dry_run={})".format(
            self.config.get("environment"), self.dry_run)


def require(port: Any, name: str) -> None:
    """Check that a port is present before using it, with a clear error."""
    from ..common.errors import ConfigError
    from ..common.i18n import t
    if port is None:
        raise ConfigError(t("msg.port.missing", name=name))


def accounts_for(associations: Sequence[str]) -> List[str]:
    """Normalise a list of Slurm associations (no blanks, no duplicates)."""
    seen: List[str] = []
    for account in associations:
        account = (account or "").strip()
        if account and account not in seen:
            seen.append(account)
    return seen
