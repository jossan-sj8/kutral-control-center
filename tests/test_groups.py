"""Groups: the standard four-step flow, and its guardrails.

The flow these tests pin down is the one the user defined:

    1. LDAP with its members from the start
    2. SSSD refresh
    3. lab directory with setgid 2770
    4. Slurm account with its members associated

And on the other side, the deletion guardrails: a group with people is not deleted, and
neither is a group that is somebody's primary one.
"""

from __future__ import annotations

import os

from modules.common.errors import EntryExists, EntryNotFound, KutralError
from modules.testing.fake_services import build_environment
from modules.groups import creation_group, deletion_group, modification_group


def _config(base_dir: str, send_mail: str = "never") -> dict:
    return {
        "environment": "lab",
        "ldap": {"server": "ldap://10.20.0.10", "base_dn": "ou=People,<SUFIJO_DEL_DIRECTORIO>",
                 "group_dn": "ou=Group,<SUFIJO_DEL_DIRECTORIO>", "root_dn": "<SUFIJO_DEL_DIRECTORIO>",
                 "manager_dn": "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>"},
        "paths": {"beegfs_home": "sandbox/mnt/beegfs/home",
                  "beegfs_labs": "sandbox/mnt/beegfs/labs",
                  "logs_dir": "sandbox/logs", "backups_dir": "sandbox/backups",
                  "mail_dir": "sandbox/mail"},
        "smtp": {"transport": "file", "sender": "hpc@ejemplo.cl", "server": "localhost", "port": 25},
        "cluster": {"name": "Kutral HPC (LAB)", "login_host": "10.20.0.20",
                    "default_shell": "/bin/bash", "nologin_shell": "/sbin/nologin",
                    "default_gid": 9000, "uid_start": 1150, "shadow_expire_permanent": -1,
                    "password_scheme": "{CRYPT}", "password_length": 12, "send_mail": send_mail},
        "slurm": {"enabled": True, "fallback_account": "hpc-default", "capture_associations": True},
        "hooks": {"after_create": [], "after_delete": [], "after_group_create": []},
        "guard_networks": ["192.0.2.0/24"],
        "_base_dir": base_dir, "_config_path": os.path.join(base_dir, "config.lab.yaml"),
    }


def _env(tmp_path, send_mail: str = "never", **kwargs):
    return build_environment(_config(str(tmp_path), send_mail), **kwargs)


def _two_users(env):
    return [u["uid"] for u in env.directory.list_users()[:2]]


# ---------------------------------------------------------------------------
# Creation: the four steps
# ---------------------------------------------------------------------------

def test_creating_a_group_completes_the_four_steps(tmp_path):
    env = _env(tmp_path)
    first, second = _two_users(env)

    result = creation_group.create_group(env, "labprueba", gid=9100, members=[first, second])

    # 1. LDAP with its members from the start
    group = env.directory.get_group("labprueba")
    assert group["gidNumber"] == "9100"
    assert sorted(group["memberUid"]) == sorted([first, second])
    # 2. SSSD
    assert ("refresh_group", "labprueba") in env.identity.calls
    # 3. lab directory with setgid
    lab = env.storage.lab("labprueba")
    assert os.path.isdir(lab)
    assert env.storage.ownership_of(lab)["mode"] == 0o2770
    assert env.storage.ownership_of(lab)["gid"] == 9100
    # 4. Slurm account and its members associated
    assert env.slurm.account_exists("labprueba")
    assert env.slurm.associations(first) == ["labprueba"]
    assert env.slurm.associations(second) == ["labprueba"]
    assert len(result["movements"]) >= 4


def test_the_directory_assigns_the_gid_when_it_is_not_asked_for(tmp_path):
    env = _env(tmp_path)
    result = creation_group.create_group(env, "otrolab")
    assert result["gid"] == 9076, "the real maximum is 9075"


def test_an_already_used_gid_is_rejected(tmp_path):
    env = _env(tmp_path)
    try:
        creation_group.create_group(env, "otrolab", gid=9000)
        raise AssertionError("it had to reject the repeated gid")
    except EntryExists as exc:
        assert "gid" in str(exc).lower()


def test_groups_differing_only_in_case_are_not_created(tmp_path):
    """`cn` is compared case-insensitively: two like that would be ambiguous.

    The real directory already has that case: `cn=lab-diez` hanging from the root and
    `cn=Lab-Diez` under `ou=Group`.
    """
    env = _env(tmp_path)
    try:
        creation_group.create_group(env, "LAB-DIEZ")
        raise AssertionError("it had to reject the collision")
    except EntryExists as exc:
        assert "mayúsculas" in str(exc)


def test_an_invalid_name_is_rejected(tmp_path):
    env = _env(tmp_path)
    for bad in ("con espacio", "con.punto", "a", "-empieza-con-guion", ""):
        try:
            creation_group.create_group(env, bad)
            raise AssertionError("it had to reject {!r}".format(bad))
        except KutralError:
            pass
    assert env.directory.actions() == []


def test_a_missing_member_stops_the_creation(tmp_path):
    env = _env(tmp_path)
    try:
        creation_group.create_group(env, "labprueba", members=["nadie"])
        raise AssertionError("it had to fail")
    except EntryNotFound:
        pass
    assert env.directory.get_group("labprueba") is None, "nothing half-done may remain"
    assert env.directory.actions() == []


def test_a_group_without_members_is_created_empty(tmp_path):
    env = _env(tmp_path)
    result = creation_group.create_group(env, "vacio")
    assert env.directory.get_group("vacio")["gidNumber"]
    assert "memberUid" not in env.directory.get_group("vacio")
    assert os.path.isdir(env.storage.lab("vacio"))
    assert env.slurm.account_exists("vacio")
    assert result["members"] == []


def test_no_lab_directory_when_it_is_not_a_lab(tmp_path):
    env = _env(tmp_path)
    creation_group.create_group(env, "nogrupal", is_lab=False)
    assert not os.path.isdir(env.storage.lab("nogrupal"))


def test_the_simulation_does_not_create_the_group(tmp_path):
    env = _env(tmp_path)
    env.dry_run = True
    result = creation_group.create_group(env, "labprueba", members=_two_users(env))
    assert result["group"] == "labprueba"
    assert env.directory.get_group("labprueba") is None
    assert env.directory.actions() == []
    assert env.slurm.calls == []
    assert not os.path.isdir(env.storage.lab("labprueba"))


def test_describing_a_group_joins_its_data(tmp_path):
    env = _env(tmp_path)
    first, second = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100, members=[first, second])

    info = creation_group.describe_group(env, "labprueba")

    assert info["gid"] == "9100"
    assert info["member_count"] == 2
    assert info["lab_exists"] is True
    assert info["slurm_account"] is True
    text = creation_group.render_group(env, "labprueba")
    assert "labprueba" in text and "9100" in text
    assert "no se encontr" in creation_group.render_group(env, "no-existe").lower()


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def test_adding_members_associates_them_in_slurm_and_is_idempotent(tmp_path):
    env = _env(tmp_path)
    first, second = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100)

    first_pass = modification_group.add_members(env, "labprueba", [first, second])
    second_pass = modification_group.add_members(env, "labprueba", [first])

    assert first_pass["added"] == [first, second]
    assert second_pass["added"] == [] and second_pass["already"] == [first]
    assert sorted(env.directory.get_group("labprueba")["memberUid"]) == sorted([first, second])
    assert env.slurm.associations(first) == ["labprueba"]


def test_adding_a_missing_member_reports_it(tmp_path):
    env = _env(tmp_path)
    first, _ = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100)
    result = modification_group.add_members(env, "labprueba", [first, "nadie"])
    assert result["added"] == [first] and result["missing"] == ["nadie"]


def test_removing_members(tmp_path):
    env = _env(tmp_path)
    first, second = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100, members=[first, second])

    result = modification_group.remove_members(env, "labprueba", [first])

    assert result["removed"] == [first]
    assert env.directory.get_group("labprueba")["memberUid"] == [second]
    assert first not in (env.directory.get_group("labprueba").get("memberUid") or [])


def test_whoever_has_that_group_as_primary_cannot_be_removed(tmp_path):
    """They would be left with a `gidNumber` pointing at a group they are not in."""
    env = _env(tmp_path)
    from modules.users import modification

    user = [u for u in env.directory.list_users() if u.get("departmentNumber")][0]
    creation_group.create_group(env, "labprueba", gid=9100)
    modification.change_group(env, user["uid"], "labprueba")

    result = modification_group.remove_members(env, "labprueba", [user["uid"]])

    assert result["removed"] == []
    assert result["skipped_primary"] == [user["uid"]]
    assert user["uid"] in env.directory.get_group("labprueba")["memberUid"]


def test_removing_from_slurm_keeps_the_other_accounts(tmp_path):
    env = _env(tmp_path)
    first, _ = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100, members=[first])
    env.slurm.register_user(first, "otro-lab")

    result = modification_group.remove_members(env, "labprueba", [first], drop_slurm=True)

    assert result["removed"] == [first]
    assert env.slurm.associations(first) == ["otro-lab"], "the other accounts must survive"


def test_removing_somebody_who_was_not_there_changes_nothing(tmp_path):
    env = _env(tmp_path)
    first, _ = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100)
    result = modification_group.remove_members(env, "labprueba", [first])
    assert result["not_members"] == [first] and result["removed"] == []


# ---------------------------------------------------------------------------
# Deletion with guardrails
# ---------------------------------------------------------------------------

def test_a_group_with_members_is_not_deleted(tmp_path):
    env = _env(tmp_path)
    first, second = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100, members=[first, second])

    try:
        deletion_group.delete_group(env, "labprueba")
        raise AssertionError("it had to refuse")
    except KutralError as exc:
        assert first in str(exc) and second in str(exc), "it must say who is affected"
    assert env.directory.get_group("labprueba") is not None


def test_a_group_that_is_somebodys_primary_one_is_not_deleted(tmp_path):
    """Even with no members in `memberUid`, somebody may have it as their gidNumber."""
    env = _env(tmp_path)
    creation_group.create_group(env, "labprueba", gid=9100)
    user = env.directory.list_users()[0]
    # It is assigned as their primary group without going through memberUid: that is
    # exactly the case being tested.
    env.directory.update(env.directory.user_dn(user["uid"]), {"gidNumber": "9100"})

    try:
        deletion_group.delete_group(env, "labprueba")
        raise AssertionError("it had to refuse")
    except KutralError as exc:
        assert "primario" in str(exc)
    assert env.directory.get_group("labprueba") is not None


def test_deleting_with_force_keeps_the_directory_and_warns(tmp_path):
    env = _env(tmp_path)
    first, _ = _two_users(env)
    creation_group.create_group(env, "labprueba", gid=9100, members=[first])

    result = deletion_group.delete_group(env, "labprueba", force=True)

    assert env.directory.get_group("labprueba") is None
    assert result["slurm_account_removed"] is True
    assert os.path.isdir(env.storage.lab("labprueba")), "the directory is kept"
    assert result["lab_warning"] and "conservó" in result["lab_warning"]
    assert result["members_at_delete"] == [first]


def test_deleting_with_the_directory_included(tmp_path):
    env = _env(tmp_path)
    creation_group.create_group(env, "labprueba", gid=9100)
    result = deletion_group.delete_group(env, "labprueba", remove_lab_dir=True)
    assert result["lab_removed"] is True
    assert not os.path.isdir(env.storage.lab("labprueba"))
    assert result["lab_warning"] is None


def test_deleting_a_missing_group_says_so(tmp_path):
    env = _env(tmp_path)
    try:
        deletion_group.delete_group(env, "no-existe")
        raise AssertionError("it had to fail")
    except EntryNotFound:
        pass


def test_the_simulation_does_not_delete(tmp_path):
    env = _env(tmp_path)
    # The group is really created and only the deletion is simulated: under simulation
    # there would be no group to delete, and the test would measure the wrong case.
    creation_group.create_group(env, "labprueba", gid=9100)
    calls_before = len(env.slurm.calls)
    actions_before = list(env.directory.actions())
    env.dry_run = True

    result = deletion_group.delete_group(env, "labprueba")

    assert result["deleted"] is True
    assert env.directory.get_group("labprueba") is not None
    # **No** new call is added: the previous ones belong to the creation.
    assert len(env.slurm.calls) == calls_before
    assert env.directory.actions() == actions_before
