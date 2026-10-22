"""Account modification, with a focus on changing group.

The central case is this: moving a user from one group to another has to touch **four**
places (gidNumber, memberUid, departmentNumber and the Slurm account). Touch only one and
the user goes on lying about their group in the other three —and on this cluster that meant,
for months, that "change the group" changed nothing.

Note on the assertions: the change labels (`Grupo`, `Curso`) and the `(vacío)` value come
from the message catalog, which the suite exercises in `es`.
"""

from __future__ import annotations

import os

from modules.common.errors import EntryExists, EntryNotFound, KutralError
from modules.core import accounts
from modules.testing.fake_services import build_environment
from modules.users import modification


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
        "hooks": {"after_create": [], "after_delete": []},
        "guard_networks": ["192.0.2.0/24"],
        "_base_dir": base_dir, "_config_path": os.path.join(base_dir, "config.lab.yaml"),
    }


def _env(tmp_path, send_mail: str = "never", **kwargs):
    return build_environment(_config(str(tmp_path), send_mail), **kwargs)


def _active_user(env) -> dict:
    return [u for u in env.directory.list_users() if not accounts.is_blocked(u)][0]


def _another_group(env, current):
    return [g["cn"] for g in env.directory.list_groups() if g["cn"] != current][0]


# ---------------------------------------------------------------------------
# Changing group
# ---------------------------------------------------------------------------

def test_change_group_moves_all_three_things(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    previous = modification.primary_group(env, user)
    new = _another_group(env, previous)

    result = modification.change_group(env, uid, new)

    updated = env.directory.get_user(uid)
    new_group = env.directory.get_group(new)
    assert str(updated["gidNumber"]) == str(new_group["gidNumber"])
    assert updated["departmentNumber"] == new
    assert uid in (new_group.get("memberUid") or [])
    assert result["from"] == previous and result["to"] == new


def test_change_group_removes_the_user_from_the_previous_group(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    previous = modification.primary_group(env, user)
    new = _another_group(env, previous)

    modification.change_group(env, uid, new)

    assert uid not in (env.directory.get_group(previous).get("memberUid") or [])


def test_change_group_keeping_the_previous_one_as_secondary(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    previous = modification.primary_group(env, user)
    new = _another_group(env, previous)

    modification.change_group(env, uid, new, keep_old=True)

    assert uid in (env.directory.get_group(previous).get("memberUid") or [])
    # Watch out: memberships() returns GROUP NAMES, not users. Comparing the uid against
    # that list gives False every time. A mistake made and fixed here.
    assert previous in env.directory.memberships(uid)
    assert new in env.directory.memberships(uid)


def test_change_group_verifies_the_result(tmp_path):
    """Writing and trusting is no good: the directory is read back and checked."""
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    new = _another_group(env, modification.primary_group(env, user))

    verification = modification.change_group(env, uid, new)["verified"]

    assert verification["gid_ok"] is True
    assert verification["label_ok"] is True
    assert verification["member_ok"] is True
    assert new in verification["memberships"]


def test_change_group_writes_the_backup_before_touching(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    new = _another_group(env, modification.primary_group(env, user))

    modification.change_group(env, user["uid"], new)

    actions = env.directory.actions()
    assert actions[0] == "save_entry"
    assert "update" in actions


def test_change_group_reassociates_slurm_and_keeps_the_other_accounts(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    previous = modification.primary_group(env, user)
    new = _another_group(env, previous)
    env.slurm.users[uid] = [previous, "other-lab"]

    result = modification.change_group(env, uid, new)

    assert ("register_user", uid, new) in env.slurm.calls
    assert new in env.slurm.associations(uid)
    assert "other-lab" in env.slurm.associations(uid), "the other accounts must not be lost"
    assert new in result["slurm_accounts"]


def test_changing_to_a_missing_group_fails_with_a_hint(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    try:
        modification.change_group(env, user["uid"], "missing-lab")
        raise AssertionError("it had to fail")
    except EntryNotFound as exc:
        assert "ou=Group" in str(exc)
        assert "lab-diez" in str(exc), "the hint about the group hanging off the root"


def test_change_group_in_simulation_touches_nothing(tmp_path):
    env = _env(tmp_path, send_mail="always")
    env.dry_run = True
    user = _active_user(env)
    uid = user["uid"]
    before = env.directory.get_user(uid)
    new = _another_group(env, modification.primary_group(env, user))

    result = modification.change_group(env, uid, new)

    assert result["changed"] is True
    assert env.directory.get_user(uid) == before
    assert env.directory.actions() == []
    assert env.slurm.calls == []
    assert env.mailer.calls == []


# ---------------------------------------------------------------------------
# Modifying attributes
# ---------------------------------------------------------------------------

def test_modifying_simple_attributes_sends_one_mail_with_the_list(tmp_path):
    env = _env(tmp_path, send_mail="always")
    user = _active_user(env)

    result = modification.modify_user(env, user["uid"],
                                      {"mail": "nuevo@ejemplo.cl", "employeeType": "postdoc"})

    assert result["changed"] is True
    assert len(result["changes"]) == 2
    assert env.directory.get_user(user["uid"])["mail"] == "nuevo@ejemplo.cl"
    assert env.mailer.kinds() == ["modification"]
    sent = env.mailer.last()["context"]["changes"]
    assert any("Correo" in item[0] for item in sent)


def test_modifying_with_no_real_change_writes_nothing(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    result = modification.modify_user(env, user["uid"], {"mail": user["mail"]})
    assert result["changed"] is False
    assert env.directory.actions() == []


def test_modifying_rejects_attributes_that_do_not_belong(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    for change in ({"uidNumber": "9999"}, {"gidNumber": "9001"}):
        try:
            modification.modify_user(env, user["uid"], change)
            raise AssertionError("it had to reject {}".format(list(change)))
        except KutralError:
            pass


def test_modifying_does_not_allow_changing_the_group_through_the_back_door(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    try:
        modification.modify_user(env, user["uid"], {"departmentNumber": "otro"})
        raise AssertionError("it had to reject the loose label change")
    except KutralError as exc:
        assert "change_group" in str(exc)


def test_modifying_validates_the_mail_and_the_shell(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    for change in ({"mail": "no-at-sign"}, {"loginShell": "bash"}, {"cn": "   "}):
        try:
            modification.modify_user(env, user["uid"], change)
            raise AssertionError("it had to reject {}".format(list(change)))
        except KutralError:
            pass


# ---------------------------------------------------------------------------
# Secondary memberships
# ---------------------------------------------------------------------------

def test_adding_and_removing_membership(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    primary = modification.primary_group(env, user)
    # A group the user is not a member of yet: otherwise "add" changes nothing and the
    # test would be measuring the wrong case.
    already_member = set(env.directory.memberships(uid))
    secondary = [g["cn"] for g in env.directory.list_groups()
                 if g["cn"] != primary and g["cn"] not in already_member][0]

    first = modification.add_membership(env, uid, secondary)
    second = modification.add_membership(env, uid, secondary)
    assert first["changed"] is True and second["changed"] is False
    assert secondary in env.directory.memberships(uid)

    removed = modification.remove_membership(env, uid, secondary)
    assert removed["changed"] is True
    assert uid not in (env.directory.get_group(secondary).get("memberUid") or [])


def test_it_cannot_be_removed_from_the_primary_group(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    primary = modification.primary_group(env, user)
    try:
        modification.remove_membership(env, user["uid"], primary)
        raise AssertionError("it had to refuse")
    except KutralError as exc:
        assert "primario" in str(exc)


# ---------------------------------------------------------------------------
# Renaming the username
# ---------------------------------------------------------------------------

def test_renaming_moves_all_four_places(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    uid = user["uid"]
    groups = env.directory.memberships(uid)
    env.slurm.users[uid] = ["lab-06", "other-lab"]
    env.storage.ensure_home(uid, int(user["uidNumber"]), int(user["gidNumber"]))

    result = modification.rename_username(env, uid, "new_uid")

    # 1. the DN
    assert env.directory.get_user(uid) is None
    assert env.directory.get_user("new_uid") is not None
    assert result["dn"].startswith("uid=new_uid,")
    # 2. the memberUid of every group
    for group in groups:
        members = env.directory.get_group(group).get("memberUid") or []
        assert uid not in members and "new_uid" in members
    # 3. Slurm
    assert sorted(env.slurm.associations("new_uid")) == ["lab-06", "other-lab"]
    assert env.slurm.associations(uid) == []
    # 4. the home
    assert os.path.isdir(env.storage.home("new_uid"))
    assert not os.path.isdir(env.storage.home(uid))


def test_renaming_to_an_existing_uid_fails(tmp_path):
    env = _env(tmp_path)
    active = [u for u in env.directory.list_users() if not accounts.is_blocked(u)]
    try:
        modification.rename_username(env, active[0]["uid"], active[1]["uid"])
        raise AssertionError("it had to fail")
    except EntryExists:
        pass


def test_renaming_validates_the_format(tmp_path):
    env = _env(tmp_path)
    user = _active_user(env)
    # `accented_á` is rejected because usernames are derived with no accents; the others,
    # because of the space, the leading digit and the empty string.
    for invalid in ("accented_á", "with space", "1number", ""):
        try:
            modification.rename_username(env, user["uid"], invalid)
            raise AssertionError("it had to reject {!r}".format(invalid))
        except KutralError:
            pass


def test_renaming_in_simulation_touches_nothing(tmp_path):
    env = _env(tmp_path)
    env.dry_run = True
    user = _active_user(env)
    result = modification.rename_username(env, user["uid"], "other_uid")
    assert result["new_username"] == "other_uid"
    assert env.directory.get_user(user["uid"]) is not None
    assert env.directory.get_user("other_uid") is None
    assert env.directory.actions() == []


def test_describe_change_is_readable(tmp_path):
    assert modification.describe_change(("Grupo", "lab-07", "lab-06")) == \
        "Grupo: lab-07 -> lab-06"
    assert modification.describe_change(("Curso", None, "Bioinfo")) == "Curso: (vacío) -> Bioinfo"
