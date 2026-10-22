"""Contract of the `Directory` port, exercised against the fake directory.

These tests are what makes development possible without a cluster: they pin down the
behaviour the domain expects (lookups, creations, modifications, renaming, membership)
so that the real ldap3 adapter has a contract to compare itself against in the lab.
"""

from __future__ import annotations

import pytest

from modules.common.errors import DirectoryError, EntryExists, EntryNotFound


def test_the_seed_has_the_real_shape_of_the_cluster(directory):
    users = directory.list_users()
    assert len(users) == 214

    uids = sorted(int(user["uidNumber"]) for user in users)
    assert uids[0] == 1041
    assert uids[-1] == 1271

    shells = {user["loginShell"] for user in users}
    assert shells == {"/bin/bash", "/sbin/nologin"}

    blocked = [user for user in users if user["loginShell"] == "/sbin/nologin"]
    assert len(blocked) == 62

    homes = {user["homeDirectory"].rsplit("/", 1)[0] for user in users}
    assert homes == {"sandbox/mnt/beegfs/home"}

    # The accented values are the ones that broke the old base64 decoder.
    # `.get()` is used because in the real directory 5 of 214 accounts have no `o`.
    assert any("Autónoma" in user.get("o", "") for user in users)


def test_lookup_by_exact_uid(directory):
    someone = directory.list_users()[0]["uid"]
    found = directory.get_user(someone)
    assert found is not None
    assert found["uid"] == someone


def test_partial_search_by_name_and_mail(directory):
    someone = directory.list_users()[0]
    by_name = directory.search_users(str(someone["cn"]).split()[0])
    assert any(user["uid"] == someone["uid"] for user in by_name)

    by_mail = directory.search_users(str(someone["mail"]).split("@")[0])
    assert any(user["uid"] == someone["uid"] for user in by_mail)


def test_missing_user(empty_directory):
    assert empty_directory.get_user("nobody") is None
    assert empty_directory.search_users("nobody") == []
    with pytest.raises(EntryNotFound):
        empty_directory.update(empty_directory.user_dn("nobody"), {"mail": "x@y.cl"})


def test_create_user_hashes_the_password_and_does_not_duplicate(directory):
    dn = directory.create_user({
        "uid": "ptest",
        "cn": "Prueba Test",
        "sn": "Test",
        "uidNumber": str(directory.next_uid()),
        "gidNumber": "9000",
        "mail": "ptest@ejemplo.cl",
        "homeDirectory": "sandbox/mnt/beegfs/home/ptest",
        "loginShell": "/bin/bash",
        "userPassword": "ClaveTemp123!",
    })
    created = directory.get_user("ptest")
    assert created is not None
    assert created["userPassword"].startswith("{CRYPT}$6$")
    assert "ClaveTemp123!" not in created["userPassword"], "the password must not be stored in clear text"
    with pytest.raises(EntryExists):
        directory.create_user({"uid": "ptest"})
    assert dn.endswith("ou=People,<SUFIJO_DEL_DIRECTORIO>")


def test_next_uid_and_gid(directory):
    assert directory.next_uid() == 1272          # real max 1271 + 1
    assert directory.next_gid() == 9076          # real max 9075 + 1


def test_a_group_is_born_with_its_members(empty_directory):
    dn = empty_directory.create_group("testlab", 9100, members=["ptest", "atest"])
    group = empty_directory.get_group("testlab")
    assert group["gidNumber"] == "9100"
    assert sorted(group["memberUid"]) == ["atest", "ptest"]
    assert dn == "cn=testlab,ou=Group,<SUFIJO_DEL_DIRECTORIO>"
    with pytest.raises(EntryExists):
        empty_directory.create_group("testlab", 9101)


def test_membership_is_added_and_removed_without_duplicating(directory):
    group = directory.list_groups()[0]
    dn = group["dn"]
    before = len(group.get("memberUid") or [])

    directory.add_values(dn, {"memberUid": "ptest"})
    assert len(directory.get_group(group["cn"])["memberUid"]) == before + 1

    directory.add_values(dn, {"memberUid": "ptest"})   # idempotent
    assert len(directory.get_group(group["cn"])["memberUid"]) == before + 1

    directory.remove_values(dn, {"memberUid": "ptest"})
    assert "ptest" not in (directory.get_group(group["cn"])["memberUid"] or [])


def test_a_single_valued_memberuid_is_not_confused_with_another_name():
    """The bug that left `uprueba` outside `gprueba2` (2026-10-14).

    An attribute with a single value can arrive as a scalar, and comparing a name
    against a string is not comparing: it is looking for a substring. `"uprueba" in
    "uprueba2"` is True, so the `memberUid` was taken as present and adding the
    membership was skipped **without a word** — no error, no movement in the summary.
    """
    from modules.core.ldap_directory import values_of

    assert values_of("uprueba2") == ["uprueba2"]
    assert "uprueba" not in values_of("uprueba2"), "this is where the bug was"
    assert "uprueba" in values_of(["uprueba", "uprueba2"])
    assert values_of(None) == []
    assert values_of(["a", "b"]) == ["a", "b"]


def test_removing_a_missing_attribute_fails_as_in_ldap(directory):
    # In real LDAP, MODIFY_DELETE on something that does not exist is an error.
    # The fake one replicates it so that the tests catch the case.
    user = directory.list_users()[0]
    with pytest.raises(DirectoryError):
        directory.remove_values(directory.user_dn(user["uid"]), {"memberUid": "ptest"})


def test_renaming_a_uid_keeps_the_rest(directory):
    someone = directory.list_users()[0]
    old = someone["uid"]
    new_dn = directory.rename(directory.user_dn(old), "nuevo_uid")
    assert directory.get_user(old) is None
    renamed = directory.get_user("nuevo_uid")
    assert renamed["uidNumber"] == someone["uidNumber"]
    assert renamed["mail"] == someone["mail"]
    assert new_dn.startswith("uid=nuevo_uid,")


def test_delete_user(directory):
    someone = directory.list_users()[0]["uid"]
    directory.delete(directory.user_dn(someone))
    assert directory.get_user(someone) is None
    with pytest.raises(EntryNotFound):
        directory.delete(directory.user_dn(someone))


def test_the_log_records_the_sequence(directory):
    # It is what allows stating "the gid changed but memberUid was not touched".
    user = directory.list_users()[0]
    directory.save_entry(user["dn"])
    directory.update(user["dn"], {"gidNumber": "9001"})
    assert directory.actions() == ["save_entry", "update"]


def test_directory_protocol(empty_directory):
    from modules.core.ports import Directory
    assert isinstance(empty_directory, Directory)
