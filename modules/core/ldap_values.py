"""LDAP values: decoding, line unfolding and LDIF formatting.

This module is about **text**. Account states live in `accounts.py`.

It handles the two things that broke the historical report, and writing LDIF a real
slapd accepts.

1) The base64 decoder was badly conditioned
-------------------------------------------
The inherited code (in kutral_mgr.py and in user_mgmt.py) did:

    parts = line.split(":", 1)
    if parts[0].endswith(":"):        # <-- never True for "o:: <base64>"

For a line `o:: RXh0ZXJubyAoVSBBdXTDs25vbWEp`, `split(":", 1)` leaves
`parts[0] = "o"` and `parts[1] = ": RXh0..."`. The code looked at `parts[0]` —the
attribute name— when the `::` is **at the start of `parts[1]`**. The condition never
held and the value was stored **as raw base64**. That is where the institutions like
`': RXh0ZXJubyAoVSBBdXTDs25vbWEp'` in the Excel came from.

The correct detection is to look at the right-hand side: if the rest **starts** with
`:`, the value comes in base64.

2) Why base64 exists in this directory
--------------------------------------
It is not a whim of the server: LDIF demands it when the value has a trailing space,
an accent or a control character. The real directory has examples of both cases — an
institution with an accent and a mail with a trailing space—, so `needs_base64`
reproduces that rule and the lab seed exercises it instead of dodging it.

Note: with `ldap3` values arrive already decoded, so this module is used for the paths
that really are text — reading an LDIF backup, serialising the seed, or comparing
against the historical report.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict, List, Optional, Tuple

from ..common.i18n import t

#: Order of attempts when decoding LDAP bytes. The inherited order is kept: the
#: cluster console delivers latin-1/cp1252 when there are accents.
DECODE_ENCODINGS = ("utf-8", "latin-1", "cp1252")


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def try_decode_base64(value: str) -> Optional[str]:
    """Try to decode base64 and return text, or None if it is not valid."""
    compact = value.strip()
    if not compact:
        return None
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None
    for encoding in DECODE_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="ignore")


def decode_ldap_value(value: str) -> str:
    """Normalise a value that may come as text or as base64.

    It accepts both the `ldapsearch` format (`o:: <b64>`, without the prefix) and the
    value already extracted. If it does not come in base64, it returns it clean.
    """
    text = value.strip()
    if text.startswith("::"):
        decoded = try_decode_base64(text[2:])
        return decoded if decoded is not None else text.lstrip(":").strip()
    if text.startswith(":"):
        return text.lstrip(":").strip()
    return text


def parse_attribute_line(line: str) -> Optional[Tuple[str, str, bool]]:
    """Split an `ldapsearch` line into (attribute, value, came_in_base64).

    It is the fix for the inherited bug: what has to be checked is whether the **rest**
    starts with ':' (the '::' separator of the LDIF format), not whether the attribute
    name ends with ':'. With `line.partition(":")` the attribute never contains the
    colon.
    """
    if not line or ":" not in line:
        return None
    token, _, rest = line.partition(":")
    attribute = token.strip()
    if not attribute:
        return None
    is_base64 = rest.startswith(":")
    raw_value = rest[1:] if is_base64 else rest
    value = raw_value.strip()
    if is_base64:
        decoded = try_decode_base64(value)
        if decoded is not None:
            return attribute, decoded, True
    return attribute, value, False


def unfold_lines(text: str) -> List[str]:
    """Undo the line folding of LDIF/ldapsearch (continuations with a space)."""
    unfolded: List[str] = []
    for line in text.split("\n"):
        if line.startswith(" ") or line.startswith("\t"):
            if unfolded:
                unfolded[-1] += line.strip()
            continue
        unfolded.append(line)
    return unfolded


def parse_entry(entry_text: str) -> Dict[str, str]:
    """Turn the block of one entry into an attribute -> value dictionary.

    Attributes with more than one value end up joined by a comma, which is what the
    historical report did. To keep every value, use `parse_entry_multi`.
    """
    values: Dict[str, List[str]] = parse_entry_multi(entry_text)
    return {key: ", ".join(items) for key, items in values.items()}


def parse_entry_multi(entry_text: str) -> Dict[str, List[str]]:
    """Like `parse_entry`, but keeping every value of each attribute."""
    result: Dict[str, List[str]] = {}
    for line in unfold_lines(entry_text):
        parsed = parse_attribute_line(line)
        if parsed is None:
            continue
        attribute, value, _ = parsed
        result.setdefault(attribute, []).append(value)
    return result


def split_ldapsearch_output(text: str) -> List[str]:
    """Split the `ldapsearch` output into entries separated by a blank line."""
    return [block for block in text.split("\n\n") if block.strip()]


def read_ldif_entries(path: str) -> List[Dict[str, str]]:
    """Read an LDIF file and return one entry per block.

    It is used to read the backups (`slapcat -l`) and to diagnose why a backup ended up
    0 bytes: if the file has no entries, it shows here.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    entries: List[Dict[str, str]] = []
    for block in split_ldapsearch_output(content):
        parsed = parse_entry(block)
        if parsed.get("dn"):
            entries.append(parsed)
    return entries


# ---------------------------------------------------------------------------
# Writing LDIF
# ---------------------------------------------------------------------------

def needs_base64(value: str) -> bool:
    """True if the value has to go in base64 inside an LDIF (RFC 2849).

    It is the underlying reason why the directory has base64 values: a trailing space, an
    accent or an empty value force the encoding. Reproducing that rule is what makes the
    lab seed exercise the decoder instead of dodging it.
    """
    if value == "" or value != value.strip():
        return True
    if value[0] in " :<":
        return True
    for char in value:
        if ord(char) < 32 or ord(char) > 126:
            return True
    return False


def ldif_line(attribute: str, value: Any) -> str:
    """Format an LDIF line, encoding in base64 when it applies."""
    text = "" if value is None else str(value)
    if needs_base64(text):
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return "{}:: {}".format(attribute, encoded)
    return "{}: {}".format(attribute, text)


def entry_to_ldif(dn: str, attributes: Dict[str, Any],
                  object_classes: Optional[List[str]] = None) -> str:
    """Serialise a whole entry as LDIF (for backups or for the seed)."""
    lines = ["dn: {}".format(dn)]
    for object_class in object_classes or []:
        lines.append("objectClass: {}".format(object_class))
    for attribute in sorted(attributes):
        if attribute in ("dn", "objectClass"):
            continue
        value = attributes[attribute]
        for item in (value if isinstance(value, list) else [value]):
            lines.append(ldif_line(attribute, item))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Group identity
# ---------------------------------------------------------------------------

#: A group is expressed in three places in the directory:
#: gidNumber (primary), memberUid (membership) and departmentNumber (label).
GROUP_GID_ATTRIBUTE = "gidNumber"
GROUP_MEMBERSHIP_ATTRIBUTE = "memberUid"
GROUP_LABEL_ATTRIBUTE = "departmentNumber"


def group_labels(groups: list) -> Dict[str, list]:
    """Map `gidNumber` -> group names, for the accounts without `departmentNumber`.

    The directory has two pairs of groups with the **same** gid (9076 and 9077), so each
    gid keeps a list: keeping only the first would be inventing the data for those
    accounts.
    """
    mapa: Dict[str, list] = {}
    for grupo in groups:
        gid = str(grupo.get(GROUP_GID_ATTRIBUTE) or "").strip()
        nombre = str(grupo.get("cn") or "").strip()
        if not gid or not nombre:
            continue
        nombres = mapa.setdefault(gid, [])
        if nombre not in nombres:
            nombres.append(nombre)
    return mapa


def resolve_group_label(entry: Dict[str, Any],
                        labels: Optional[Dict[str, list]] = None) -> Optional[str]:
    """Return a user's group name, falling back to gidNumber.

    `departmentNumber` is preferred (what the bulk update introduced) and it falls back
    to `gidNumber` when the label is not populated — 17 of the 218 accounts, almost all
    created by the inherited flow, which does not write that label.

    With `labels` (see `group_labels`) the name is resolved against `ou=Group`, which is
    what the report does. Without `labels` it returns `gid:NNNN`, and whoever reads it
    knows the data is missing instead of believing the group is called that.
    """
    label = entry.get(GROUP_LABEL_ATTRIBUTE) or ""
    if isinstance(label, (list, tuple)):
        label = label[0] if label else ""
    label = str(label).strip()
    if label:
        return label
    gid = entry.get(GROUP_GID_ATTRIBUTE) or ""
    if isinstance(gid, (list, tuple)):
        gid = gid[0] if gid else ""
    gid = str(gid).strip()
    if not gid:
        return None
    nombres = list((labels or {}).get(gid) or [])
    if len(nombres) == 1:
        return nombres[0]
    if nombres:
        # Gid shared by two groups: both are shown, not one at random.
        return t("msg.group.shared_gid", names=" | ".join(sorted(nombres)), gid=gid)
    return "gid:{}".format(gid)
