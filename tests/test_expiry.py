"""The expiry policy: dates, durations and the number 20819.

`shadowExpire` is days since 1 January 1970. These tests pin that translation down —because
it is the one that makes the directory unreadable— and the ways the operator can ask for a
date.

The case that started all this: in October 2026, "end of year" is three months away. A
policy that expires every user in January forces rescheduling all of them in January, so
the default is **no expiry** and durations exist so that "one year" can be said without
recomputing dates by hand.
"""

from __future__ import annotations

import datetime

from modules.common.errors import KutralError
from modules.core import accounts, expiry

REF = datetime.date(2026, 10, 7)


# ---------------------------------------------------------------------------
# The number nobody can read
# ---------------------------------------------------------------------------

def test_the_number_20819_is_1_january_2027():
    """57 years x 365 days + 14 leap days = 20 819."""
    assert accounts.shadow_expire_date({"shadowExpire": "20819"}) == datetime.date(2027, 1, 1)
    assert accounts.date_to_shadow_expire(datetime.date(2027, 1, 1)) == 20819
    assert 57 * 365 + 14 == 20819


def test_the_round_trip_between_date_and_number():
    for day in (datetime.date(2027, 1, 1), datetime.date(2030, 6, 30),
                datetime.date(2020, 3, 15)):
        number = accounts.date_to_shadow_expire(day)
        assert accounts.shadow_expire_date({"shadowExpire": str(number)}) == day


def test_zero_is_a_sentinel_not_the_epoch_date():
    """`shadowExpire: 0` does not come back as a date: it is a marker, not 1-1-1970.

    And note what the state module does **not** do: it does not count it as blocked,
    because it only recognises the sentinel `1` (what `deactivate_user.sh` writes) and the
    no-login shell. Today no account has a `0` in the directory, so nothing changes; it is
    recorded as an **open decision**: if a `0` ever shows up, the report will show that
    account as active.
    """
    assert accounts.date_to_shadow_expire(datetime.date(1970, 1, 1)) == 0
    assert accounts.shadow_expire_date({"shadowExpire": "0"}) is None
    assert accounts.is_blocked({"shadowExpire": "0", "loginShell": "/bin/bash"}) is False
    assert accounts.is_active({"shadowExpire": "0", "loginShell": "/bin/bash"}) is True


# ---------------------------------------------------------------------------
# No expiry, and exact dates
# ---------------------------------------------------------------------------

def test_with_no_date_the_account_is_permanent():
    """It is the default: it forces nothing to be rescheduled."""
    assert expiry.parse_expiry(None, {"cluster": {}}, REF) is None
    for word in ("nunca", "permanente", "none", "-1", ""):
        assert expiry.parse_expiry(word, {"cluster": {}}, REF) is None


def test_an_exact_date():
    assert expiry.parse_expiry("2028-12-31", {}, REF) == datetime.date(2028, 12, 31)


def test_an_invalid_date_explains_itself():
    for bad in ("31-12-2028", "diciembre", "2028/12/31", "2 semanas"):
        try:
            expiry.parse_expiry(bad, {}, REF)
            raise AssertionError("it should have rejected {!r}".format(bad))
        except KutralError as exc:
            assert "2028-12-31" in str(exc), "the error must show the valid forms"


# ---------------------------------------------------------------------------
# End of year, configurable
# ---------------------------------------------------------------------------

def test_the_default_year_end_is_the_first_of_january_next():
    assert expiry.next_year_end({}, REF) == datetime.date(2027, 1, 1)
    assert expiry.parse_expiry("fin-de-anio", {}, REF) == datetime.date(2027, 1, 1)


def test_the_year_end_can_be_moved_to_december():
    """`12-31` ends before the turn of the year; `01-01` lets it through."""
    config = {"cluster": {"year_end": "12-31"}}
    assert expiry.next_year_end(config, REF) == datetime.date(2026, 12, 31)
    # And if that date has already gone by this year, it jumps to the next one.
    assert expiry.next_year_end(config, datetime.date(2027, 3, 1)) == datetime.date(2027, 12, 31)


# ---------------------------------------------------------------------------
# Durations: how a grant or a PhD is thought of
# ---------------------------------------------------------------------------

def test_durations_in_days_months_and_years():
    assert expiry.parse_expiry("90d", {}, REF) == datetime.date(2027, 1, 5)
    assert expiry.parse_expiry("6m", {}, REF) == datetime.date(2027, 4, 7)
    assert expiry.parse_expiry("18m", {}, REF) == datetime.date(2028, 4, 7)
    assert expiry.parse_expiry("2a", {}, REF) == datetime.date(2028, 10, 7)
    assert expiry.parse_expiry("1 ano", {}, REF) == datetime.date(2027, 10, 7)


def test_adding_months_adjusts_the_day_when_the_month_is_shorter():
    """31 August + 6 months cannot give 31 February."""
    assert expiry.add_months(datetime.date(2026, 8, 31), 6) == datetime.date(2027, 2, 28)
    assert expiry.add_months(datetime.date(2024, 8, 31), 6) == datetime.date(2025, 2, 28)
    assert expiry.add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)
    assert expiry.add_months(datetime.date(2026, 1, 15), 12) == datetime.date(2027, 1, 15)


# ---------------------------------------------------------------------------
# The default policy, in the configuration
# ---------------------------------------------------------------------------

def test_the_default_value_is_configurable():
    """So that `--expires 1y` does not have to be passed on every creation."""
    config = {"cluster": {"expire_default": "1a"}}
    assert expiry.parse_expiry(None, config, REF) == datetime.date(2027, 10, 7)
    # And `--expires nunca` can still override it.
    assert expiry.parse_expiry("nunca", config, REF) is None


def test_a_duration_overrides_the_default():
    config = {"cluster": {"expire_default": "1a"}}
    assert expiry.parse_expiry("3m", config, REF) == datetime.date(2027, 1, 7)


# ---------------------------------------------------------------------------
# How it is shown
# ---------------------------------------------------------------------------

def test_describe_says_how_many_days_are_left():
    assert expiry.describe(None, REF) == "sin vencimiento"
    assert expiry.describe(datetime.date(2027, 1, 1), REF) == "2027-01-01 (en 86 días)"
    assert "vencida" in expiry.describe(datetime.date(2026, 1, 1), REF)


def test_what_it_returns_can_be_written_into_the_directory():
    """The date has to end up as the number shadowExpire understands."""
    day = expiry.parse_expiry("fin-de-anio", {}, REF)
    assert accounts.date_to_shadow_expire(day) == 20819
    assert accounts.shadow_expire_date({"shadowExpire": "20819"}) == datetime.date(2027, 1, 1)
