"""Account state, derived from `shadowExpire` and `loginShell`.

The real directory has **four** different situations, not two:

    absent       -> no expiry was ever set (what add_users.sh leaves behind)
    -1           -> expiry disabled: permanent account
    1            -> expired: blocked account (what deactivate_user.sh writes)
    <date>       -> expires on a specific date (the 7 accounts with 20819 ≈ 2027-01-01)

The inherited code only distinguished `shadowExpire == 1` and treated an explicit date
as "active", so the report lied about those 7 accounts.

Also, `loginShell = /sbin/nologin` is a second blocking mechanism that
deactivate_user.sh did NOT apply but 62 accounts on the cluster have, so a coherent
state has to look at both attributes.

Two functions, two audiences: `state_key()` is the canonical value the code compares
against and never changes with the language; `state()` is the text a person reads, and
it is bilingual.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from ..common.i18n import t

NOLOGIN_SHELLS = ("/sbin/nologin", "/usr/sbin/nologin", "/bin/false", "/usr/bin/false")
EPOCH = date(1970, 1, 1)

#: Canonical state keys. The logic compares these; they do not depend on the language.
STATE_ACTIVE = "active"
STATE_BLOCKED = "blocked"
STATE_EXPIRING = "expiring"
STATE_NO_EXPIRY = "no_expiry"

#: Message key with the label of each state, for reports and console output.
STATE_MESSAGES = {
    STATE_ACTIVE: "state.active",
    STATE_BLOCKED: "state.blocked",
    STATE_EXPIRING: "state.expiring",
    STATE_NO_EXPIRY: "state.no_expiry",
}


def shadow_expire_raw(entry: Dict[str, Any]) -> Optional[str]:
    """Raw value of shadowExpire, or None if the attribute is not there."""
    value = entry.get("shadowExpire")
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def shadow_expire_days(entry: Dict[str, Any]) -> Optional[int]:
    """shadowExpire as an integer number of days since epoch, or None if unreadable."""
    raw = shadow_expire_raw(entry)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def shadow_expire_date(entry: Dict[str, Any]) -> Optional[date]:
    """Expiry date, or None if it is permanent / absent."""
    days = shadow_expire_days(entry)
    if days is None or days <= 1:
        return None
    try:
        return EPOCH + timedelta(days=days)
    except OverflowError:
        return None


def date_to_shadow_expire(when: date) -> int:
    """Convert a date to shadowExpire (days since epoch)."""
    return (when - EPOCH).days


def is_nologin(entry: Dict[str, Any]) -> bool:
    """True if the account's shell is blocked."""
    shell = entry.get("loginShell")
    if isinstance(shell, (list, tuple)):
        shell = shell[0] if shell else ""
    return str(shell or "").strip() in NOLOGIN_SHELLS


def is_blocked(entry: Dict[str, Any]) -> bool:
    """Blocked account: explicitly expired, or a no-login shell."""
    days = shadow_expire_days(entry)
    return days == 1 or is_nologin(entry)


def is_expiring(entry: Dict[str, Any]) -> bool:
    """Active account, but with an expiry date set."""
    days = shadow_expire_days(entry)
    return days is not None and days > 1


def state_key(entry: Dict[str, Any]) -> str:
    """Canonical state key: what the code should compare against."""
    if is_blocked(entry):
        return STATE_BLOCKED
    if is_expiring(entry):
        return STATE_EXPIRING
    if shadow_expire_days(entry) == -1:
        return STATE_ACTIVE
    return STATE_NO_EXPIRY


def state(entry: Dict[str, Any]) -> str:
    """State label for reports and console output, in the current language."""
    return t(STATE_MESSAGES[state_key(entry)])


def is_active(entry: Dict[str, Any]) -> bool:
    return state_key(entry) != STATE_BLOCKED


def describe(entry: Dict[str, Any]) -> str:
    """Readable explanation of the state, with the date when there is one."""
    if is_blocked(entry):
        motivos = []
        if shadow_expire_days(entry) == 1:
            motivos.append(t("state.motive.shadow_expire"))
        if is_nologin(entry):
            motivos.append(t("state.motive.nologin"))
        return t("state.describe.blocked",
                 motives=", ".join(motivos) or t("state.motive.unknown"))
    expires = shadow_expire_date(entry)
    if expires:
        return t("state.describe.until", date=expires.isoformat())
    if shadow_expire_days(entry) == -1:
        return t("state.describe.permanent")
    return t("state.describe.no_attribute")
