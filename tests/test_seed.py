"""Fidelity of the synthetic seed against the real directory.

The seed is not decoration: it stands in for the cluster. If it does not look like the
real directory, the tests pass and the code fails in production. These tests pin down
the numbers that were measured with `slapcat` on 2026-10-07.
"""

from __future__ import annotations

from modules.testing.seed import GROUP_NAMES, build_seed, summary, to_ldif


def test_counts_match_the_real_directory():
    counts = summary(build_seed())
    assert counts["users"] == 214
    assert counts["groups"] == 53
    assert counts["blocked"] == 62
    assert counts["expiring"] == 7
    # The accounts left behind by add_users.sh: no shadowExpire (17 in the real directory)
    assert counts["without_expire"] > 0
    # "Poor" entries: no givenName, the ones that came out of the inherited script
    assert counts["poor_entries"] > 0
    assert counts["without_mail"] > 0
    assert counts["without_department"] > 0
    assert counts["memberships"] > 250


def test_all_four_states_are_represented():
    from modules.core import accounts

    states = set()
    for entry in build_seed().values():
        if "posixAccount" in (entry.get("objectClass") or []):
            states.add(accounts.state_key(entry))
    assert accounts.STATE_BLOCKED in states
    assert accounts.STATE_EXPIRING in states
    assert accounts.STATE_ACTIVE in states
    assert accounts.STATE_NO_EXPIRY in states


def test_the_expiry_date_is_the_real_one():
    from modules.core import accounts

    dated = [entry for entry in build_seed().values()
             if accounts.shadow_expire_days(entry) and accounts.shadow_expire_days(entry) > 1]
    assert len(dated) == 7
    assert accounts.shadow_expire_date(dated[0]).isoformat() == "2027-01-01"


def test_the_stray_group_off_the_root_exists_and_is_unreachable_as_a_group():
    """Reproduces the finding: there is a groupOfNames outside ou=Group.

    A module that looks for groups under `ou=Group` does not find it, and that is
    exactly what happens on the cluster with `cn=lab-diez`.
    """
    entries = build_seed()
    stray = [dn for dn in entries if dn.startswith("cn=lab-diez,<SUFIJO_DEL_DIRECTORIO>")]
    assert stray, "the seed must include the group hanging off the root"
    assert "groupOfNames" in entries[stray[0]]["objectClass"]
    assert not any(dn.startswith("cn=lab-diez,ou=Group") for dn in entries)


def test_group_names_are_the_real_ones():
    entries = build_seed()
    for name in ("lab-06", "lab-07", "lab-cinco", "student", "GPRUEBA"):
        assert name in GROUP_NAMES
        assert "cn={},ou=Group,<SUFIJO_DEL_DIRECTORIO>".format(name) in entries


def test_the_serialized_seed_uses_base64_where_it_must():
    """Values with accents have to come out in base64, as on the cluster."""
    ldif = to_ldif(build_seed())
    assert "o:: " in ldif, "values with accents must go in base64"
    assert "changetype: add" in ldif
    assert "Externo (U. Autónoma)" not in ldif, "the raw value must not survive"
