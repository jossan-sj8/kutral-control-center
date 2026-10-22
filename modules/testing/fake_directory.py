"""In-memory directory: fake implementation of the `Directory` port.

It makes it possible to run **everything** in the control center with no LDAP, no
network and no cluster: the logic tests, the wizards and rehearsal mode work against this
object as if it were the real directory.

It records every write in `self.log` so the tests can assert on the *sequence* of
operations, not only on the final result. That is what makes it possible to detect things
like "it changed the gidNumber but did not touch memberUid".
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from ..common.errors import DirectoryError, EntryExists, EntryNotFound
from ..common.i18n import t
from ..common.security import hash_password


class FakeDirectory(object):
    """In-memory directory with the same interface as LdapDirectory."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, entries: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.config = config or {}
        cluster = (config or {}).get("cluster", {}) if config else {}
        self.uid_start = int(cluster.get("uid_start") or 1150)
        self.gid_start = int(cluster.get("gid_start") or cluster.get("default_gid") or 9000)
        self.scheme = str(cluster.get("password_scheme") or "{CRYPT}")
        self.user_base = ((config or {}).get("ldap", {}) or {}).get("base_dn", "ou=People,<SUFIJO_DEL_DIRECTORIO>")
        self.group_base = ((config or {}).get("ldap", {}) or {}).get("group_dn", "ou=Group,<SUFIJO_DEL_DIRECTORIO>")
        #: Uids of deleted accounts: they are never reassigned (see `retire_uid`).
        self.retired: Set[int] = set()
        self.entries: Dict[str, Dict[str, Any]] = {}
        self.log: List[Dict[str, Any]] = []
        for dn, attributes in (entries or {}).items():
            self.entries[dn.lower()] = dict(attributes, dn=dn)

    # -------------------------------------------------------------- internals
    def _note(self, action: str, dn: str, payload: Any = None) -> None:
        self.log.append({"action": action, "dn": dn, "payload": payload})

    def actions(self) -> List[str]:
        """Sequence of recorded actions, without detail (for readable asserts)."""
        return [item["action"] for item in self.log]

    def _values(self, entry: Dict[str, Any], attribute: str) -> List[str]:
        value = entry.get(attribute)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return [str(value)]

    def _set(self, entry: Dict[str, Any], attribute: str, value: Any) -> None:
        entry[attribute] = value

    # ----------------------------------------------------------------- reading
    def _users(self) -> List[Dict[str, Any]]:
        return [entry for dn, entry in self.entries.items()
                if dn.startswith("uid=") and "posixAccount" in self._values(entry, "objectClass")]

    def _groups(self) -> List[Dict[str, Any]]:
        return [entry for dn, entry in self.entries.items()
                if dn.startswith("cn=") and "posixGroup" in self._values(entry, "objectClass")]

    def get_user(self, uid: str) -> Optional[Dict[str, Any]]:
        entry = self.entries.get(self.user_dn(uid).lower())
        return dict(entry) if entry else None

    def user_exists(self, uid: str) -> bool:
        return self.get_user(uid) is not None

    def search_users(self, term: str) -> List[Dict[str, Any]]:
        term = (term or "").strip().lower()
        if not term:
            return self.list_users()
        hits = []
        for entry in self._users():
            uid = str(entry.get("uid", "")).lower()
            cn = str(entry.get("cn", "")).lower()
            mail = str(entry.get("mail", "")).lower()
            if term == uid or term in uid or term in cn or term in mail:
                hits.append(dict(entry))
        return hits

    def list_users(self) -> List[Dict[str, Any]]:
        return [dict(entry) for entry in self._users()]

    def get_group(self, name: str) -> Optional[Dict[str, Any]]:
        entry = self.entries.get(self.group_dn(name).lower())
        return dict(entry) if entry else None

    def group_exists(self, name: str) -> bool:
        return self.get_group(name) is not None

    def list_groups(self) -> List[Dict[str, Any]]:
        return [dict(entry) for entry in self._groups()]

    def memberships(self, username: str) -> List[str]:
        """Groups whose memberUid includes the user.

        Careful: in this directory it **normally includes the primary group too**,
        because the inherited flow (`add_users.sh`) adds the user to the memberUid of the
        same group it assigns through `gidNumber`. It is not a seed mistake: it is how the
        real directory is, and that is why the domain cannot assume that "being in
        memberUid" means "secondary group".
        """
        encontrados = []
        for entry in self._groups():
            if username in self._values(entry, "memberUid"):
                encontrados.append(str(entry.get("cn")))
        return sorted(encontrados)

    def add_member(self, group: str, username: str) -> bool:
        """Add the memberUid. Returns True only if something changed."""
        entry = self.entries.get(self.group_dn(group).lower())
        if entry is None:
            raise EntryNotFound(t("msg.group.not_found.short", group=group))
        if username in self._values(entry, "memberUid"):
            return False
        # `add_values` is used so the log records the same action as in the real adapter,
        # and the tests can assert on the sequence.
        self.add_values(entry["dn"], {"memberUid": username})
        return True

    def remove_member(self, group: str, username: str) -> bool:
        """Remove the memberUid. Returns True only if something changed.

        Unlike `remove_values`, it **does not fail** if the user was not a member: the
        domain's question is "did anything change?", and the answer to "remove somebody
        who is not there" is that nothing changed.
        """
        entry = self.entries.get(self.group_dn(group).lower())
        if entry is None:
            raise EntryNotFound(t("msg.group.not_found.short", group=group))
        if username not in self._values(entry, "memberUid"):
            return False
        self.remove_values(entry["dn"], {"memberUid": username})
        return True

    def next_uid(self) -> int:
        used = []
        for entry in self._users():
            for value in self._values(entry, "uidNumber"):
                if value.isdigit():
                    used.append(int(value))
        # Retired uids count as used: the history folder and the orphan files carry the
        # number, not the name.
        used.extend(self.retired)
        return max(self.uid_start, max(used) + 1) if used else self.uid_start

    def retired_uids(self) -> List[int]:
        return sorted(self.retired)

    def retire_uid(self, uid: Any, username: Optional[str] = None) -> None:
        try:
            self.retired.add(int(uid))
        except (TypeError, ValueError):
            return
        self._note("retire_uid", str(uid), {"username": username})

    def next_gid(self) -> int:
        used = []
        for entry in self._groups():
            for value in self._values(entry, "gidNumber"):
                if value.isdigit():
                    used.append(int(value))
        return max(self.gid_start, max(used) + 1) if used else self.gid_start

    # ------------------------------------------------------------------- names
    def user_dn(self, uid: str) -> str:
        return "uid={},{}".format(uid, self.user_base)

    def group_dn(self, name: str) -> str:
        return "cn={},{}".format(name, self.group_base)

    # ----------------------------------------------------------------- writing
    def create_user(self, attributes: Dict[str, Any]) -> str:
        uid = attributes.get("uid")
        if not uid:
            raise DirectoryError(t("msg.directory.needs_uid"))
        if self.user_exists(uid):
            raise EntryExists(t("msg.account.exists.short", username=uid))
        dn = self.user_dn(uid)
        payload = dict(attributes, dn=dn)
        payload.setdefault("objectClass", ["inetOrgPerson", "posixAccount", "shadowAccount"])
        password = payload.get("userPassword")
        if password and not str(password).startswith("{"):
            payload["userPassword"] = hash_password(str(password), scheme=self.scheme)
        self.entries[dn.lower()] = payload
        self._note("create_user", dn, {"uid": uid, "uidNumber": payload.get("uidNumber"),
                                       "gidNumber": payload.get("gidNumber")})
        return dn

    def create_group(self, name: str, gid: int, members: Optional[List[str]] = None) -> str:
        if self.group_exists(name):
            raise EntryExists(t("msg.group.exists.short", group=name))
        dn = self.group_dn(name)
        payload: Dict[str, Any] = {"dn": dn, "objectClass": ["top", "posixGroup"],
                                   "cn": name, "gidNumber": str(gid)}
        if members:
            payload["memberUid"] = list(members)
        self.entries[dn.lower()] = payload
        self._note("create_group", dn, {"gid": gid, "members": list(members or [])})
        return dn

    def update(self, dn: str, changes: Dict[str, Any]) -> None:
        entry = self.entries.get(dn.lower())
        if entry is None:
            raise EntryNotFound(t("msg.not_found.short", dn=dn))
        for key, value in changes.items():
            self._set(entry, key, value)
        self._note("update", dn, dict(changes))

    def add_values(self, dn: str, changes: Dict[str, Any]) -> None:
        entry = self.entries.get(dn.lower())
        if entry is None:
            raise EntryNotFound(t("msg.not_found.short", dn=dn))
        for key, value in changes.items():
            current = self._values(entry, key)
            for item in (value if isinstance(value, list) else [value]):
                if str(item) not in current:
                    current.append(str(item))
            self._set(entry, key, current if len(current) > 1 else (current[0] if current else None))
        self._note("add_values", dn, dict(changes))

    def remove_values(self, dn: str, changes: Dict[str, Any]) -> None:
        entry = self.entries.get(dn.lower())
        if entry is None:
            raise EntryNotFound(t("msg.not_found.short", dn=dn))
        for key, value in changes.items():
            drop = [str(item) for item in (value if isinstance(value, list) else [value])]
            if key not in entry:
                # Real LDAP: MODIFY_DELETE on an attribute that does not exist is an
                # error. It is replicated so the tests catch the case, as in production.
                raise DirectoryError(t("msg.attribute.missing_for_delete",
                                       attribute=key, dn=dn))
            remaining = [item for item in self._values(entry, key) if item not in drop]
            self._set(entry, key, remaining if remaining else None)
        self._note("remove_values", dn, dict(changes))

    def set_password(self, dn: str, password: str) -> None:
        entry = self.entries.get(dn.lower())
        if entry is None:
            raise EntryNotFound(t("msg.not_found.short", dn=dn))
        entry["userPassword"] = hash_password(password, scheme=self.scheme)
        self._note("set_password", dn, {"user": dn.split(",", 1)[0]})

    def rename(self, dn: str, new_uid: str) -> str:
        entry = self.entries.get(dn.lower())
        if entry is None:
            raise EntryNotFound(t("msg.not_found.short", dn=dn))
        if self.user_exists(new_uid):
            raise EntryExists(t("msg.account.exists.short", username=new_uid))
        del self.entries[dn.lower()]
        new_dn = self.user_dn(new_uid)
        entry["dn"] = new_dn
        entry["uid"] = new_uid
        self.entries[new_dn.lower()] = entry
        self._note("rename", dn, {"new_dn": new_dn})
        return new_dn

    def delete(self, dn: str) -> None:
        if dn.lower() not in self.entries:
            raise EntryNotFound(t("msg.not_found.short", dn=dn))
        del self.entries[dn.lower()]
        self._note("delete", dn)

    def save_entry(self, dn: str, for_restore: bool = False) -> str:
        entry = self.entries.get(dn.lower())
        if entry is None:
            raise EntryNotFound(t("msg.backup_failed.short", dn=dn))
        self._note("save_entry", dn, {"for_restore": for_restore})
        return "/dev/null/fake-backup-{}.ldif".format(dn.split(",", 1)[0].replace("=", "-"))

    # ------------------------------------------------------------- persistence
    def save_state(self, path: str) -> str:
        """Write the directory into a JSON so rehearsal survives the command.

        Without this, every CLI invocation would start from the seed and it would not be
        possible, for instance, to create an account and query it afterwards. It is what
        makes rehearsal mode useful to walk a multi-step flow.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.entries, handle, indent=1, ensure_ascii=False, sort_keys=True)
        return path

    @classmethod
    def cargar_estado(cls, config: Optional[Dict[str, Any]], path: str) -> "FakeDirectory":
        """Rebuild the directory from a state file."""
        with open(path, "r", encoding="utf-8") as handle:
            entries = json.load(handle)
        return cls(config, entries)
