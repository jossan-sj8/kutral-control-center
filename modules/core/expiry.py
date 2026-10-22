"""Expiry policy: interpret what the operator writes, and compute dates.

`shadowExpire` is **days since 1 January 1970**, not a date and not a state. That is
why 20819 means 2027-01-01, and why nobody writes it by hand.

The policy lives here and **not** in the command code, because a hardcoded policy is a
policy that cannot be changed without editing and redeploying. The configuration
defines two things:

    cluster.expire_default   what happens when NO date is asked for ("nunca" by default)
    cluster.year_end         what "end of year" means (MM-DD; 01-01 by default)

And the operator can write any of these forms, in either language:

    (nothing)              -> uses `expire_default`; with "nunca"/"never", no expiry
    nunca / never          -> permanent (the attribute is removed)
    2028-12-31             -> an exact date
    fin-de-anio / year-end -> the next occurrence of `year_end`
    2a / 2y, 18m, 90d      -> durations, which is how a grant or a PhD is thought of

Why durations matter: in October 2026, "end of year" is three months away. If the real
policy is "students stay for the academic year", one should be able to write
`--expires 1y` instead of a date that has to be recomputed by hand every time.
"""

from __future__ import annotations

import calendar
import datetime
import re
from typing import Any, Dict, Optional

from ..common.errors import KutralError
from ..common.i18n import t
from . import config as cfgmod

#: Duration: "90d"/"90d", "18m", "2a"/"2y". Singular and plural are both accepted.
DURATION_PATTERN = re.compile(
    r"^(\d+)\s*(d|dia|dias|day|days|m|mes|meses|month|months|a|ano|anos|y|year|years)$")

#: What counts as permanent, in both languages.
PERMANENT_WORDS = ("", "nunca", "never", "none", "permanente", "permanent",
                   "sin-vencimiento", "-1")

#: What "end of year" means if the configuration says nothing else.
DEFAULT_YEAR_END = "01-01"

#: The ways the operator can write "end of year", in both languages.
YEAR_END_WORDS = ("fin-de-anio", "findeanio", "fin_de_anio", "fin-de-ano", "year-end",
                  "yearend", "year_end", "eoy")


def add_months(base: datetime.date, months: int) -> datetime.date:
    """Add months, adjusting the day when the target month is shorter.

    Without the adjustment, 31 August + 6 months would blow up: February has no 31st.
    """
    total = base.month - 1 + months
    year = base.year + total // 12
    month = total % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def next_year_end(config: Optional[Dict[str, Any]] = None,
                  reference: Optional[datetime.date] = None) -> datetime.date:
    """The next occurrence of `cluster.year_end`.

    With the default value (`01-01`) and a reference of October 2026, it gives
    2027-01-01. With `12-31` it would give 2026-12-31: the difference is whether the
    account has to survive the turn of the year or not.
    """
    today = reference or datetime.date.today()
    text = str(cfgmod.get(config or {}, "cluster.year_end", DEFAULT_YEAR_END)
               or DEFAULT_YEAR_END)
    try:
        month, day = (int(part) for part in text.split("-")[:2])
    except (ValueError, TypeError):
        month, day = 1, 1
    month = min(max(month, 1), 12)
    day = min(max(day, 1), calendar.monthrange(today.year, month)[1])
    candidate = datetime.date(today.year, month, day)
    if candidate <= today:
        day = min(day, calendar.monthrange(today.year + 1, month)[1])
        candidate = datetime.date(today.year + 1, month, day)
    return candidate


def parse_expiry(value: Optional[str], config: Optional[Dict[str, Any]] = None,
                 reference: Optional[datetime.date] = None) -> Optional[datetime.date]:
    """Interpret what the operator wrote. Returns a date or None (permanent)."""
    today = reference or datetime.date.today()
    text = str(value or "").strip().lower()

    if not text:
        text = str(cfgmod.get(config or {}, "cluster.expire_default", "nunca")
                   or "nunca").strip().lower()

    if text in PERMANENT_WORDS:
        return None

    if text in YEAR_END_WORDS:
        return next_year_end(config, today)

    match = DURATION_PATTERN.match(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("d"):
            return today + datetime.timedelta(days=amount)
        if unit.startswith("m"):
            return add_months(today, amount)
        return add_months(today, 12 * amount)

    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise KutralError(t("msg.expiry.invalid", value=value))


def describe(expires: Optional[datetime.date], reference: Optional[datetime.date] = None) -> str:
    """Readable text to show back, with the days left."""
    if expires is None:
        return t("msg.no_expiry")
    today = reference or datetime.date.today()
    days = (expires - today).days
    if days < 0:
        return t("msg.expiry.overdue", date=expires.isoformat(), days=-days)
    return t("msg.expiry.in_days", date=expires.isoformat(), days=days)
