"""Synthetic data replicating the real shape of the directory.

Taken from the `slapcat` of 2026-10-07 and the report of 2026-09-08, so that the tests
exercise the same ranges, values and odd cases of the cluster **without using real
people's data**:

    accounts          214 posixAccount         (one of them is the canary)
    groups             53 posixGroup + 1 groupOfNames hanging from the root
    uidNumber         1041 .. 1271
    gidNumber         1108, 9000 .. 9050, 9075
    loginShell        /bin/bash and /sbin/nologin
    shadowExpire      -1, 1, 20819 (2027-01-01) and **absent**
    homeDirectory     /mnt/beegfs/home/<user>
    employeeType      includes 'Student' and 'student', and the typo 'reserach'
    o                 includes 'UOH', 'Externo' and 'Externo (U. Autónoma)'  <- accented
    departmentNumber  the group name (lab-06 and company)
    <CUENTA_ADMINISTRADORA>        organizationalRole with a password

The **inconsistencies** of the real directory are reproduced too, because if the code
does not tolerate them here it will not tolerate them in production:

  - ~16 "poor" entries with no `givenName`/`displayName` and with `sn` = full name
    (the inherited script's bug, which writes the whole name into `sn`).
  - Accounts with no `mail` and no `departmentNumber`.
  - A `groupOfNames` (`cn=lab-diez`) hanging from the root instead of `ou=Group`:
    a module that looks for groups under `ou=Group` does not find it, and that is
    exactly what happens on the cluster.
  - Values with accents and with a trailing space, which force base64 in LDIF.

It is a **snapshot of 2026-10-07**: the directory kept moving (by 2026-10-08 the real
maximum was `uidNumber` 1283 and `gidNumber` 9082, against 1271 and 9075 here). The model
is not updated every time the roll changes —it fixes shapes and odd cases, not the day's
numbers—; that is what the checks against the cluster are for.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from ..common.i18n import t
from ..common.security import hash_password
from ..core.ldap_values import ldif_line

#: Vocabulary observed in production (inconsistencies included).
ACCOUNT_TYPES = ["student", "Student", "academic", "research", "PhD student",
                 "postdoc", "engineer", "medical", "reserach"]  # 'reserach' is real
INSTITUTIONS = ["UOH", "ICI", "Externo", "Externo (U. Autónoma)", "ICS",
                "externo", "Externo (U. de Chile)"]

#: Example groups. The real directory has 53; the names here are fictitious, keeping
#: the oddities that matter: mixed capitalisation, a hyphen, an underscore and the four
#: `gprueba*`, which are groups with no Slurm account.
GROUP_NAMES = [
    # `lab-06` goes second on purpose: the seed hands out gids **by position**, and a test
    # asserts that the gid of `lab-06` is 9000 — the second slot of `GROUP_GIDS`.
    "lab-uno", "lab-06", "lab-07", "lab-dos", "lab-tres", "lab-cuatro",
    "lab-cinco", "lab-08", "lab-09", "lab-10", "lab-11", "lab-12", "lab-13",
    "lab-14", "lab-15", "lab-16", "lab-17", "lab-18", "lab-19", "lab-20",
    "lab-21", "lab-22", "lab-23", "lab-24", "lab-25", "lab-26", "lab-27",
    "lab-28", "lab-29", "lab-30", "lab-31", "lab-32", "lab-33", "lab-34",
    "lab-35", "lab-36", "lab-37", "lab-38", "lab-39", "lab-40", "lab-41",
    "lab-42", "lab_43", "lab-44-alt", "Lab-Diez",
    "gprueba2", "gprueba3", "gprueba4", "GPRUEBA", "pd1", "pd2", "student",
    "windowsvm",
]

#: Real gids of the directory, one per group. The maximum stays at 9075.
GROUP_GIDS: List[int] = [1108] + list(range(9000, 9051)) + [9075]

FIRST_NAMES = ["ana", "bruno", "carola", "diego", "elena", "felipe", "gabriela",
               "hugo", "ines", "javier", "karina", "luis", "maria", "nicolas",
               "olga", "pedro", "quimey", "rocio", "sergio", "tomas", "ursula",
               "valentina", "walter", "ximena", "yazmin", "zoe"]
LAST_NAMES = ["alarcon", "bravo", "castillo", "diaz", "escobar", "fuentes",
              "gonzalez", "hinojosa", "ibarra", "jara", "krause", "lara",
              "mendoza", "nunez", "oyarce", "pizarro", "quiroz", "rojas",
              "salinas", "tapia", "urrutia", "vera", "zapata"]

#: Expiry date observed on 7 real accounts (days since epoch).
EXPIRE_2027 = 20819

TOTAL_USERS = 214
BLOCKED_USERS = 62
EXPIRING_USERS = 7
UID_MIN = 1041
UID_MAX = 1271

#: Unverifiable password: the lab does not authenticate, and computing 214 real
#: SHA-512 hashes would slow every test down without adding anything.
PLACEHOLDER_HASH = ("{CRYPT}$6$saltsaltsaltsalt$"
                    "hashsintetico0000000000000000000000000000000000")


def _uids(users: int, rng: random.Random) -> List[int]:
    """`users` uids inside the real range, with both ends fixed.

    1041 and 1271 are fixed because the real directory occupies exactly that range, and
    there are tests that depend on the sequence starting and ending there.
    """
    if users >= (UID_MAX - UID_MIN + 1):
        return list(range(UID_MIN, UID_MAX + 1))
    interior = rng.sample(range(UID_MIN + 1, UID_MAX), users - 2)
    return [UID_MIN] + sorted(interior) + [UID_MAX]


def build_seed(config: Optional[Dict[str, Any]] = None, users: int = TOTAL_USERS,
               seed: int = 20261007) -> Dict[str, Dict[str, Any]]:
    """Build the whole synthetic directory.

    It returns {dn: attributes}, ready for `FakeDirectory(entries=...)` or to be dumped
    to LDIF and imported into a test slapd.
    """
    ldap = (config or {}).get("ldap", {}) or {}
    cluster = (config or {}).get("cluster", {}) or {}
    paths = (config or {}).get("paths", {}) or {}
    user_base = ldap.get("base_dn", "ou=People,<SUFIJO_DEL_DIRECTORIO>")
    group_base = ldap.get("group_dn", "ou=Group,<SUFIJO_DEL_DIRECTORIO>")
    root_dn = ldap.get("root_dn", "<SUFIJO_DEL_DIRECTORIO>")
    home_base = paths.get("beegfs_home", "/mnt/beegfs/home")
    default_shell = cluster.get("default_shell", "/bin/bash")
    nologin_shell = cluster.get("nologin_shell", "/sbin/nologin")

    rng = random.Random(seed)
    entries: Dict[str, Dict[str, Any]] = {}

    # --- base structure ------------------------------------------------------
    entries[root_dn] = {"dn": root_dn, "objectClass": ["top", "dcObject", "organization"],
                        "dc": "srv", "o": "Kutral"}
    entries["ou=People,{}".format(root_dn)] = {
        "dn": "ou=People,{}".format(root_dn),
        "objectClass": ["top", "organizationalUnit"], "ou": "People"}
    entries["ou=Group,{}".format(root_dn)] = {
        "dn": "ou=Group,{}".format(root_dn),
        "objectClass": ["top", "organizationalUnit"], "ou": "Group"}

    # --- admin ---------------------------------------------------------------
    manager_dn = "<CUENTA_ADMINISTRADORA>,{}".format(root_dn)
    entries[manager_dn] = {
        "dn": manager_dn, "objectClass": ["top", "organizationalRole"],
        "cn": "Manager", "sn": "Manager",
        "userPassword": hash_password("Demo#ClaveFicticia", salt="demodemo12345678")}

    # --- the group hanging from the root (it exists like this in production) --
    stray_dn = "cn=lab-diez,{}".format(root_dn)
    entries[stray_dn] = {
        "dn": stray_dn, "objectClass": ["top", "groupOfNames"],
        "cn": "lab-diez", "member": "uid={}@placeholder".format("ana")}

    # --- groups --------------------------------------------------------------
    gid_to_group: Dict[int, str] = {}
    for position, name in enumerate(GROUP_NAMES):
        gid = GROUP_GIDS[position % len(GROUP_GIDS)]
        gid_to_group[gid] = name
        entries["cn={},{}".format(name, group_base)] = {
            "dn": "cn={},{}".format(name, group_base),
            "objectClass": ["top", "posixGroup"],
            "cn": name,
            "gidNumber": str(gid),
        }

    # --- users ---------------------------------------------------------------
    available = _uids(users, rng)
    members_by_group: Dict[str, List[str]] = {name: [] for name in GROUP_NAMES}

    for position, uid_number in enumerate(available):
        first = FIRST_NAMES[position % len(FIRST_NAMES)]
        last = LAST_NAMES[(position * 7) % len(LAST_NAMES)]
        username = "{}{}".format(first[0], last)[:11]
        if any(entry.get("uid") == username for entry in entries.values()):
            username = "{}{}{}".format(first[0], last, position % 100)[:11]

        group_name = GROUP_NAMES[position % len(GROUP_NAMES)]
        gid_number = GROUP_GIDS[position % len(GROUP_GIDS)]
        full_name = "{} {}".format(first.capitalize(), last.capitalize())

        blocked = position < BLOCKED_USERS
        expiring = not blocked and position < BLOCKED_USERS + EXPIRING_USERS
        # "Poor" entries: the ones that came out of the inherited script, which does not
        # set givenName/displayName/gecos and writes the full name into `sn`.
        poor = position > 0 and position % 13 == 0

        entry: Dict[str, Any] = {
            "dn": "uid={},{}".format(username, user_base),
            "objectClass": ["inetOrgPerson", "posixAccount", "shadowAccount"],
            "uid": username,
            "cn": full_name,
            "sn": full_name if poor else last.capitalize(),
            "uidNumber": str(uid_number),
            "gidNumber": str(gid_number),
            "homeDirectory": "{}/{}".format(home_base, username),
            "loginShell": nologin_shell if blocked else default_shell,
            "userPassword": PLACEHOLDER_HASH,
        }
        if not poor:
            entry["givenName"] = first.capitalize()
            entry["displayName"] = full_name
            if position % 2 == 0:
                entry["gecos"] = full_name
        # Position 0 is always complete: there are tests that read the first user of the
        # list to search by name and by mail.
        if position == 0 or position % 27 != 3:
            entry["mail"] = "{}@{}".format(
                username, rng.choice(["ejemplo.cl", "pregrado.ejemplo.cl", "gmail.com"]))
        if position == 0 or position % 15 != 4:
            entry["departmentNumber"] = group_name
        entry["employeeType"] = ACCOUNT_TYPES[position % len(ACCOUNT_TYPES)]
        if position > 0 and position % 21 == 6:
            pass  # account with no institution, like 5 of the 214 real ones
        else:
            entry["o"] = INSTITUTIONS[position % len(INSTITUTIONS)]

        if blocked:
            entry["shadowExpire"] = "1"
        elif expiring:
            entry["shadowExpire"] = str(EXPIRE_2027)
        elif position % 3:
            entry["shadowExpire"] = "-1"
        # The rest are left WITHOUT shadowExpire, like the accounts add_users.sh leaves.

        entries[entry["dn"]] = entry
        members_by_group.setdefault(group_name, []).append(username)

    # --- membership ----------------------------------------------------------
    # In this directory membership is computed **before** writing the groups. Doing it
    # the other way round (write and then add extras) wipes the extras already added on
    # every overwrite: it is an easy mistake to make and a silent one.
    #
    # Real order of magnitude: 252 memberUid mentions across 53 groups, of which 214
    # are each account's primary one — the inherited flow also adds the user to the
    # memberUid of their primary group, not only through gidNumber.
    extras_by_group: Dict[str, List[str]] = {name: [] for name in GROUP_NAMES}
    for group_name, members in members_by_group.items():
        for username in members[: max(1, len(members) // 4)]:
            other = rng.choice([name for name in GROUP_NAMES if name != group_name])
            extras_by_group[other].append(username)

    for group_name in GROUP_NAMES:
        primary = members_by_group[group_name]
        secondary = [u for u in extras_by_group[group_name] if u not in primary]
        members = primary + secondary
        if members:
            entries["cn={},{}".format(group_name, group_base)]["memberUid"] = members

    # The group hanging from the root points at a real user of the seed.
    entries[stray_dn]["member"] = entries["uid={},{}".format(
        members_by_group[GROUP_NAMES[0]][0], user_base)]["dn"]

    return entries


def to_ldif(entries: Dict[str, Dict[str, Any]], base_dn: str = "<SUFIJO_DEL_DIRECTORIO>") -> str:
    """Serialise the seed to LDIF so it can be imported into a test slapd.

    It uses `ldif_line`, so values with accents or with edge spaces come out in base64 —
    just like in the real directory, and unlike writing the raw value.
    """
    skip = {"dn", "objectClass"}
    lines: List[str] = [t("msg.seed.header"), t("msg.seed.generated"), ""]
    for dn in sorted(entries, key=lambda key: (key.count(","), key)):
        entry = entries[dn]
        lines.append("dn: {}".format(dn))
        lines.append("changetype: add")
        for object_class in entry.get("objectClass", []):
            lines.append("objectClass: {}".format(object_class))
        for key in sorted(entry):
            if key in skip:
                continue
            for value in (entry[key] if isinstance(entry[key], list) else [entry[key]]):
                lines.append(ldif_line(key, value))
        lines.append("")
    return "\n".join(lines) + "\n"


def summary(entries: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Seed counts, to compare them with the real directory."""
    from ..core import accounts

    counts: Dict[str, int] = {
        "entries": len(entries), "users": 0, "groups": 0, "memberships": 0,
        "blocked": 0, "expiring": 0, "without_expire": 0,
        "poor_entries": 0, "without_mail": 0, "without_department": 0,
    }
    for entry in entries.values():
        classes = entry.get("objectClass") or []
        if "posixAccount" in classes:
            counts["users"] += 1
            if accounts.is_blocked(entry):
                counts["blocked"] += 1
            elif accounts.is_expiring(entry):
                counts["expiring"] += 1
            if accounts.shadow_expire_raw(entry) is None:
                counts["without_expire"] += 1
            if "givenName" not in entry:
                counts["poor_entries"] += 1
            if "mail" not in entry:
                counts["without_mail"] += 1
            if "departmentNumber" not in entry:
                counts["without_department"] += 1
        elif "posixGroup" in classes:
            counts["groups"] += 1
            counts["memberships"] += len(entry.get("memberUid") or [])
    return counts
