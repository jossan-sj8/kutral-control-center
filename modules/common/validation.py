"""Shared validations: username, mail and name normalisation.

They used to be duplicated between creation and modification, with different rules in
each. Here there is a single source, and the rules come from measuring the real
directory:

  - usernames of 3 to 11 characters (measured: the shortest has 3, the longest 11)
  - they start with a letter or an underscore, and continue in lowercase, digits,
    hyphen or underscore
  - dots are accepted (the real directory uses them: `g.cabas`, `duvan.henao`), but
    not at the start, at the end or repeated

The same rules are used when creating and when renaming: if usernames could be created
that later cannot be renamed, the system would end up in a state it cannot leave.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, List, Optional

from .errors import KutralError
from .i18n import t

USERNAME_MIN = 3
USERNAME_MAX = 11
USERNAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_\-]*(?:\.[a-z0-9_\-]+)*$")
MAIL_PATTERN = re.compile(r"^[\w\.\-\+]+@[\w\.\-]+\.\w+$")


def slug(value: Any) -> str:
    """Normalise a text: no accents, lowercase, no punctuation.

    It is what makes it possible to propose `dmunoz` from "Diego Muñoz" without
    the accent breaking the username.
    """
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def validate_username(value: Any, taken: Optional[Iterable[str]] = None,
                      label: Optional[str] = None) -> str:
    """Validate the username. Returns the clean value."""
    text = str(value or "").strip().lower()
    if not USERNAME_PATTERN.match(text) or not USERNAME_MIN <= len(text) <= USERNAME_MAX:
        raise KutralError(t("msg.username.invalid", label=label or t("msg.username.label"),
                            value=value, min=USERNAME_MIN, max=USERNAME_MAX))
    if taken and text in set(taken):
        raise KutralError(t("msg.username.taken", value=text))
    return text


def validate_mail(value: Any) -> str:
    """Validate a mail address. Returns the clean value."""
    text = str(value or "").strip()
    if not MAIL_PATTERN.match(text):
        raise KutralError(t("msg.mail.invalid", value=value))
    return text


def suggest_username(fullname: str, taken: Optional[Iterable[str]] = None) -> str:
    """Propose a username in the cluster's style: first initial + surname.

    With "Diego Muñoz" it proposes `dmunoz`; with "Iván Prado", `iprado`. If it
    is already taken, it appends a number — as any system that creates accounts does,
    and as the real directory shows (`gprueba2`, `gprueba3`, `gprueba4`).
    """
    parts = slug(fullname).split()
    if not parts:
        raise KutralError(t("msg.username.none", fullname=fullname))
    base = (parts[0][0] + (parts[1] if len(parts) > 1 else parts[0][1:] or ""))[:USERNAME_MAX]
    used = {str(item).lower() for item in (taken or [])}
    if base not in used:
        return base
    for number in range(2, 100):
        candidate = "{}{}".format(base[: USERNAME_MAX - len(str(number))], number)
        if candidate not in used:
            return candidate
    raise KutralError(t("msg.username.no_free", fullname=fullname))


def split_name(fullname: str) -> List[str]:
    """Split a full name into (given name, surnames).

    The inherited script took the first word as `givenName` and **the last one** as
    `sn`, and it also wrote the whole name into `sn`. Here it is split properly:
    everything after the given name is the surnames, which in Chile are usually two.
    """
    parts = str(fullname or "").split()
    if not parts:
        raise KutralError(t("msg.fullname.empty"))
    if len(parts) == 1:
        return [parts[0], parts[0]]
    return [parts[0], " ".join(parts[1:])]
