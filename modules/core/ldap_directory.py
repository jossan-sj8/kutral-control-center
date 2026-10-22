"""Real LDAP adapter, on top of ldap3.

It implements the `Directory` port from core/ports.py. Two things it replaces from the
inherited flow:

1. **No more subprocess.** `ldapsearch`/`ldapmodify`/`ldappasswd` are gone, and with
them the Manager password travelling on the command line (`ldapmodify -w
"$LDAP_PASS"`), which stayed visible in `ps`.
2. **No more manual base64 decoding.** The previous code's bug (`"o::
RXh0...".split(":", 1)` never detected the `::`) corrupted 2 rows of the report.
With ldap3 values arrive already decoded by construction.

Every write goes to the address configured in `ldap.server`, which is the directory's
single master (verified: no replication, no contextCSN).
"""

from __future__ import annotations

import os

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import ldap3

from ..common.errors import DirectoryError, EntryExists, EntryNotFound
from ..common.i18n import t
from ..common.security import hash_password
from . import accounts as accounts_mod
from . import config as cfgmod

# Attributes requested when reading an account. It is the set observed in the real
# directory (iprado) plus the ones the new code needs in order to create.
USER_ATTRIBUTES = [
    "uid", "cn", "sn", "givenName", "displayName", "gecos",
    "uidNumber", "gidNumber", "mail", "homeDirectory", "loginShell",
    "employeeType", "o", "ou", "departmentNumber", "description",
    "shadowExpire", "shadowLastChange", "userPassword", "objectClass",
]

GROUP_ATTRIBUTES = ["cn", "gidNumber", "memberUid", "description", "objectClass"]

FILTER_SPECIAL = "\\*()\0"


def escape_filter(value: str) -> str:
    """Escape a value so it can be interpolated into an LDAP filter (RFC 4515)."""
    out = []
    for char in str(value):
        if char in FILTER_SPECIAL:
            out.append("\\{:02x}".format(ord(char)))
        else:
            out.append(char)
    return "".join(out)


def _as_text(value: Any) -> Any:
    """Normalise single-value lists and turn everything into text."""
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        if len(value) == 1:
            return _as_text(value[0])
        return [_as_text(item) for item in value]
    if value is None:
        return None
    return str(value)


def entry_to_dict(entry: Any) -> Dict[str, Any]:
    """Turn an ldap3 entry into a plain-text dictionary."""
    data: Dict[str, Any] = {}
    try:
        for attribute in entry.entry_attributes:
            data[str(attribute)] = _as_text(entry[attribute].value)
    except Exception as exc:  # pragma: no cover - entrada malformada
        raise DirectoryError(t("msg.directory.entry_unreadable", entry=entry, error=exc))
    data["dn"] = str(entry.entry_dn)
    return data


def values_of(value: Any) -> List[str]:
    """Normalise a directory attribute into a list of texts.

    An attribute with **a single value** may arrive as a scalar, and comparing a name
    against a string is not comparing: it is looking for a substring. That is how
    `uprueba` ended up outside `gprueba2`: `"uprueba" in "uprueba2"` is `True`, the
    `memberUid` was taken as present and the membership was skipped without a word. It
    is **always normalised to a list** before comparing.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


class LdapDirectory(object):
    """Real implementation of the Directory port."""

    def __init__(self, config: Dict[str, Any], connection: ldap3.Connection,
                 backups_dir: Optional[str] = None) -> None:
        self.config = config
        self.conn = connection
        self.user_base = config["ldap"]["base_dn"]
        self.group_base = config["ldap"]["group_dn"]
        self.backups_dir = backups_dir or cfgmod.path_for(config, "backups_dir")

    # ------------------------------------------------------------- connection
    @classmethod
    def connect(cls, config: Dict[str, Any], password: Optional[str] = None,
                interactive: bool = True) -> "LdapDirectory":
        """Open the connection and return the adapter ready to use."""
        secret = password or cfgmod.resolve_ldap_password(config, interactive=interactive)
        uri = config["ldap"]["server"]
        timeout = int(config["ldap"].get("timeout") or 10)
        try:
            server = ldap3.Server(uri, connect_timeout=timeout)
            connection = ldap3.Connection(
                server,
                user=config["ldap"]["manager_dn"],
                password=secret,
                auto_bind=True,
                raise_exceptions=True,
                receive_timeout=timeout,
            )
        except Exception as exc:
            raise DirectoryError(t("msg.directory.connect_failed", server=uri,
                                    user=config["ldap"]["manager_dn"], error=exc))
        return cls(config, connection)

    def close(self) -> None:
        try:
            self.conn.unbind()
        except Exception:
            pass

    # ------------------------------------------------------------------ reading
    def _search(self, base: str, ldap_filter: str, attributes: Sequence[str]) -> List[Dict[str, Any]]:
        try:
            found = self.conn.search(
                search_base=base, search_filter=ldap_filter,
                search_scope=ldap3.SUBTREE, attributes=list(attributes))
        except Exception as exc:
            raise DirectoryError(t("msg.directory.search_failed", search=ldap_filter,
                                    base=base, error=exc))
        if not found:
            return []
        return [entry_to_dict(entry) for entry in self.conn.entries]

    def get_user(self, uid: str) -> Optional[Dict[str, Any]]:
        results = self._search(
            self.user_base, "(uid={})".format(escape_filter(uid)), USER_ATTRIBUTES)
        return results[0] if results else None

    def search_users(self, term: str) -> List[Dict[str, Any]]:
        term = (term or "").strip()
        if not term:
            return self.list_users()
        escaped = escape_filter(term)
        ldap_filter = ("(|(uid={exact})(cn=*{partial}*)(mail=*{partial}*)(uid=*{partial}*))"
                       .format(exact=escaped, partial=escaped))
        return self._search(self.user_base, ldap_filter, USER_ATTRIBUTES)

    def list_users(self) -> List[Dict[str, Any]]:
        return self._search(self.user_base, "(objectClass=posixAccount)", USER_ATTRIBUTES)

    def user_exists(self, uid: str) -> bool:
        return self.get_user(uid) is not None

    def get_group(self, name: str) -> Optional[Dict[str, Any]]:
        results = self._search(
            self.group_base, "(cn={})".format(escape_filter(name)), GROUP_ATTRIBUTES)
        return results[0] if results else None

    def list_groups(self) -> List[Dict[str, Any]]:
        return self._search(self.group_base, "(objectClass=posixGroup)", GROUP_ATTRIBUTES)

    def group_exists(self, name: str) -> bool:
        return self.get_group(name) is not None

    def memberships(self, username: str) -> List[str]:
        """Groups whose memberUid includes the user.

        It is resolved with a filter, not by walking the 53 groups. It includes the
        primary group when the directory lists it there — which is the norm on this
        cluster, because of how `add_users.sh` creates them.
        """
        encontrados = []
        for entry in self._search(
                self.group_base, "(memberUid={})".format(escape_filter(username)), ["cn"]):
            if entry.get("cn"):
                encontrados.append(str(entry["cn"]))
        return sorted(encontrados)

    def add_member(self, group: str, username: str) -> bool:
        """Add the memberUid with MODIFY_ADD. Returns True only if something changed.

        The group is read first so as not to report a change that did not exist: adding
        someone who is already there is not a change, and saying so would be just as
        wrong.
        """
        entry = self.get_group(group)
        if entry is None:
            raise EntryNotFound(t("msg.group.not_found", group=group))
        if username in values_of(entry.get("memberUid")):
            return False
        self.add_values(entry["dn"], {"memberUid": username})
        return True

    def remove_member(self, group: str, username: str) -> bool:
        """Remove the memberUid with MODIFY_DELETE. Returns True only if something changed.

        `remove_values` is never reached if the user was not a member: on a real LDAP
        that would be a "no such attribute" error, and removing someone who is not there
        is not an error, it is a non-change.
        """
        entry = self.get_group(group)
        if entry is None:
            raise EntryNotFound(t("msg.group.not_found", group=group))
        if username not in values_of(entry.get("memberUid")):
            return False
        self.remove_values(entry["dn"], {"memberUid": username})
        return True

    def next_uid(self) -> int:
        """Next free uid, without reusing those of already deleted accounts.

        The policy is "maximum in use + 1", but that reassigns the uid of the last
        deleted account — and with the number, the ownership of its history folder and
        of the orphan files left behind in BeeGFS. See `retire_uid`.
        """
        siguiente = self._next_number(
            self.user_base, "(objectClass=posixAccount)", "uidNumber",
            int(self.config["cluster"].get("uid_start") or 1150))
        retirados = self.retired_uids()
        return max([siguiente] + [uid + 1 for uid in retirados])

    # -------------------------------------------------------- retired uids
    def _retired_file(self) -> Optional[str]:
        return os.path.join(self.backups_dir, "uids-retirados.txt") if self.backups_dir else None

    def retired_uids(self) -> List[int]:
        """Uids recorded as retired. One line per uid: `uid user date`."""
        ruta = self._retired_file()
        if not ruta or not os.path.exists(ruta):
            return []
        uids: List[int] = []
        try:
            with open(ruta, "r", encoding="utf-8") as handle:
                for line in handle:
                    partes = line.split()
                    if not partes:
                        continue
                    try:
                        uids.append(int(partes[0]))
                    except ValueError:
                        continue
        except OSError:
            return []
        return uids

    def retire_uid(self, uid: Any, username: Optional[str] = None) -> None:
        """Record the uid so it is never reassigned. It never interrupts a deletion.

        If the file cannot be written it warns and goes on: the account is already
        deleted, and aborting over the record would leave the deletion half done.
        """
        from datetime import datetime, timezone

        from ..common import ui

        try:
            numero = int(uid)
        except (TypeError, ValueError):
            return
        ruta = self._retired_file()
        if not ruta or numero in self.retired_uids():
            return
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "a", encoding="utf-8") as handle:
                handle.write("{} {} {}\n".format(
                    numero, username or "-",
                    datetime.now(timezone.utc).isoformat(timespec="seconds")))
            os.chmod(ruta, 0o600)
        except OSError as exc:
            ui.warn(t("msg.directory.retired_uid_failed", uid=numero, error=exc))

    def next_gid(self) -> int:
        return self._next_number(
            self.group_base, "(objectClass=posixGroup)", "gidNumber",
            int(self._gid_start()))

    def _gid_start(self) -> int:
        """Floor of the gid distribution (9000 when it is not configured).

        The old name `default_gid` is still accepted, which said "default group" when it
        really is only the floor: 9000 is `lab-07`'s gid. If somebody had set it as
        "default group", removing the key without warning would be worse than reading
        it.
        """
        cluster = self.config.get("cluster") or {}
        return int(cluster.get("gid_start") or cluster.get("default_gid") or 9000)

    def _next_number(self, base: str, ldap_filter: str, attribute: str, start: int) -> int:
        """Next free id = maximum in use + 1 (same policy as the current flow)."""
        used = set()
        for entry in self._search(base, ldap_filter, [attribute]):
            value = entry.get(attribute)
            for item in (value if isinstance(value, list) else [value]):
                try:
                    used.add(int(item))
                except (TypeError, ValueError):
                    continue
        if not used:
            return start
        return max(start, max(used) + 1)

    # ------------------------------------------------------------------- names
    def user_dn(self, uid: str) -> str:
        return "uid={},{}".format(uid, self.user_base)

    def group_dn(self, name: str) -> str:
        return "cn={},{}".format(name, self.group_base)

    # ----------------------------------------------------------------- writing
    def _check(self, operation: str, dn: str) -> None:
        if not operation:
            description = ""
            try:
                description = self.conn.result.get("description", "")
            except Exception:
                pass
            raise DirectoryError(t("msg.directory.rejected", dn=dn,
                                    error=description or t("msg.no_detail")))

    def create_user(self, attributes: Dict[str, Any]) -> str:
        uid = attributes.get("uid")
        if not uid:
            raise DirectoryError(t("msg.directory.needs_uid"))
        if self.user_exists(uid):
            raise EntryExists(t("msg.account.exists", username=uid))
        dn = self.user_dn(uid)
        payload = dict(attributes)
        object_classes = payload.pop("objectClass", ["inetOrgPerson", "posixAccount", "shadowAccount"])
        payload.pop("dn", None)
        if "userPassword" in payload and payload["userPassword"] and not str(payload["userPassword"]).startswith("{"):
            payload["userPassword"] = hash_password(
                str(payload["userPassword"]),
                scheme=str(self.config["cluster"].get("password_scheme") or "{CRYPT}"))
        self._check(self.conn.add(dn, list(object_classes), payload), dn)
        return dn

    def create_group(self, name: str, gid: int, members: Optional[List[str]] = None) -> str:
        if self.group_exists(name):
            raise EntryExists(t("msg.directory.group_exists", group=name))
        dn = self.group_dn(name)
        attributes: Dict[str, Any] = {"cn": name, "gidNumber": str(gid)}
        if members:
            # memberUid from the start: that way the group is born with its members and
            # no later pass is needed (which is what the old flow did).
            attributes["memberUid"] = list(members)
        self._check(self.conn.add(dn, ["top", "posixGroup"], attributes), dn)
        return dn

    def update(self, dn: str, changes: Dict[str, Any]) -> None:
        payload = {key: [(ldap3.MODIFY_REPLACE, value if isinstance(value, list) else [value])]
                   for key, value in changes.items()}
        self._check(self.conn.modify(dn, payload), dn)

    def add_values(self, dn: str, changes: Dict[str, Any]) -> None:
        payload = {key: [(ldap3.MODIFY_ADD, value if isinstance(value, list) else [value])]
                   for key, value in changes.items()}
        self._check(self.conn.modify(dn, payload), dn)

    def remove_values(self, dn: str, changes: Dict[str, Any]) -> None:
        payload = {key: [(ldap3.MODIFY_DELETE, value if isinstance(value, list) else [value])]
                   for key, value in changes.items()}
        self._check(self.conn.modify(dn, payload), dn)

    def set_password(self, dn: str, password: str) -> None:
        scheme = str(self.config["cluster"].get("password_scheme") or "{CRYPT}")
        self.update(dn, {"userPassword": hash_password(password, scheme=scheme)})

    def rename(self, dn: str, new_uid: str) -> str:
        try:
            done = self.conn.modify_dn(dn, "uid={}".format(new_uid), delete_old_dn=True)
        except Exception as exc:
            raise DirectoryError(t("msg.directory.rename_failed", dn=dn, uid=new_uid,
                                    error=exc))
        self._check(done, dn)
        return self.user_dn(new_uid)

    def delete(self, dn: str) -> None:
        self._check(self.conn.delete(dn), dn)

    # -------------------------------------------------------------- rollback
    def save_entry(self, dn: str, for_restore: bool = False) -> str:
        """Write an LDIF with the current entry, so it can be reverted by hand.

        It is the cheapest safety net: before touching an account, its previous state is
        left on disk.

        `for_restore=True` —what deletion uses— writes the `ldapadd` format, which
        **recreates** the entry with its `objectClass`. The `ldapmodify` format is good
        for reverting a change, but not for creating again what is no longer there:
        without this, the backup of a deletion could not be reapplied.
        """
        from datetime import datetime, timezone

        attributes = USER_ATTRIBUTES if dn.startswith("uid=") else GROUP_ATTRIBUTES
        results = self._search(dn.split(",")[1], "(dn={})".format(dn), attributes) if False else None
        entry = None
        for candidate in self._search(dn.split(",", 1)[1], "({})".format(dn.split(",", 1)[0]), attributes):
            if candidate.get("dn", "").lower() == dn.lower():
                entry = candidate
                break
        if entry is None:
            raise EntryNotFound(t("msg.directory.backup_missing", dn=dn))
        if not self.backups_dir:
            raise DirectoryError(t("msg.directory.no_backups_dir"))
        os.makedirs(self.backups_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        name = "{}-{}.ldif".format(dn.split(",", 1)[0].replace("=", "-"), stamp)
        path = os.path.join(self.backups_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(t("msg.directory.backup_header") + "\n")
            handle.write("# {}\n\n".format(datetime.now(timezone.utc).isoformat(timespec="seconds")))
            handle.write("dn: {}\n".format(entry.get("dn", dn)))
            if for_restore:
                # Recreates the entry as it was: it is reapplied with `ldapadd -f`.
                handle.write("changetype: add\n")
                for key, value in sorted(entry.items()):
                    if key == "dn":
                        continue
                    for item in (value if isinstance(value, list) else [value]):
                        handle.write("{}: {}\n".format(key, item))
            else:
                # Reverts a change: it is reapplied with `ldapmodify -f`.
                handle.write("changetype: modify\n")
                for key, value in sorted(entry.items()):
                    if key in ("dn", "objectClass"):
                        continue
                    handle.write("replace: {}\n".format(key))
                    for item in (value if isinstance(value, list) else [value]):
                        handle.write("{}: {}\n".format(key, item))
                    handle.write("-\n")
        return path
