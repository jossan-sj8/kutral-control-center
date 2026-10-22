"""The four account states of `shadowExpire`.

The inherited code only told "active" from "blocked", and with that it reported the 7
accounts expiring on 01-01-2027 as active. These tests pin the correct behaviour down.
"""

from __future__ import annotations

from datetime import date

from modules.core import accounts


def test_absent_is_active_with_no_expiry():
    assert accounts.state_key({}) == accounts.STATE_NO_EXPIRY
    assert accounts.is_active({}) is True
    assert "sin shadowExpire" in accounts.describe({})


def test_minus_one_is_permanent():
    entry = {"shadowExpire": "-1"}
    assert accounts.state_key(entry) == accounts.STATE_ACTIVE
    assert accounts.shadow_expire_date(entry) is None
    assert "permanente" in accounts.describe(entry)


def test_one_is_blocked():
    assert accounts.state_key({"shadowExpire": "1"}) == accounts.STATE_BLOCKED
    assert accounts.is_active({"shadowExpire": "1"}) is False


def test_an_explicit_date_is_active_with_expiry():
    entry = {"shadowExpire": "20819"}
    assert accounts.state_key(entry) == accounts.STATE_EXPIRING
    assert accounts.is_active(entry) is True
    assert accounts.shadow_expire_date(entry) == date(2027, 1, 1)
    assert accounts.describe(entry) == "Activo hasta 2027-01-01"


def test_nologin_blocks_even_when_not_expired():
    entry = {"loginShell": "/sbin/nologin"}
    assert accounts.is_blocked(entry) is True
    assert accounts.state_key(entry) == accounts.STATE_BLOCKED
    assert "shell de no-login" in accounts.describe(entry)


def test_both_mechanisms_are_reported_together():
    entry = {"shadowExpire": "1", "loginShell": "/sbin/nologin"}
    assert "shadowExpire=1" in accounts.describe(entry)
    assert "shell de no-login" in accounts.describe(entry)


def test_date_round_trip():
    target = date(2027, 1, 1)
    assert accounts.date_to_shadow_expire(target) == 20819
    assert accounts.shadow_expire_date(
        {"shadowExpire": str(accounts.date_to_shadow_expire(target))}) == target


def test_a_garbage_value_does_not_blow_up():
    entry = {"shadowExpire": "no-es-un-numero"}
    assert accounts.shadow_expire_days(entry) is None
    assert accounts.is_active(entry) is True


def test_a_single_value_list_is_normalised():
    assert accounts.shadow_expire_days({"shadowExpire": ["1"]}) == 1
