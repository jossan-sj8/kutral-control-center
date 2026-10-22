"""Account creation and consultation: the two ends of the lifecycle.

Creation is the operation with the most steps and the one that costs the most when it is
left half-done: if the account is created and the mail does not go out, the person has no
credentials and nobody notices. That is why everything is validated up front, and every
step is checked afterwards.

The consultation joins the four sources —LDAP, Slurm, storage and local identity— because
the real problem is not reading LDAP: it is that the same person looks different depending
on where you ask.
"""

from __future__ import annotations

import datetime
import json
import os

from modules.common.errors import EntryExists, EntryNotFound, KutralError
from modules.common.validation import split_name, suggest_username, validate_username
from modules.core import accounts
from modules.core.audit import AuditLog
from modules.testing.fake_services import build_environment
from modules.users import consultation, creation


def _config(base_dir: str, send_mail: str = "never", hooks=None) -> dict:
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
        "hooks": {"after_create": hooks or [], "after_delete": []},
        "guard_networks": ["192.0.2.0/24"],
        "_base_dir": base_dir, "_config_path": os.path.join(base_dir, "config.lab.yaml"),
    }


def _env(tmp_path, send_mail: str = "never", hooks=None, **kwargs):
    return build_environment(_config(str(tmp_path), send_mail, hooks), **kwargs)


def _data(**overrides) -> dict:
    base = {"fullname": "Diego Muñoz Salas", "username": "dmunozs",
            "group": "lab-06", "mail": "diego@ejemplo.cl",
            "employee_type": "student", "institute": "UOH"}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Validations
# ---------------------------------------------------------------------------

def test_the_username_rules_match_the_real_directory():
    # Measured: the shortest username has 3 characters and the longest 11.
    assert validate_username("abc") == "abc"
    assert validate_username("a" * 11) == "a" * 11
    # The dot is accepted: the real directory has `g.cabas` and `duvan.henao`.
    assert validate_username("g.cabas") == "g.cabas"
    assert validate_username("duvan.henao") == "duvan.henao"
    for invalid in ("ab", "a" * 12, "ConMayuscula", ".conpunto", "con..punto",
                    "con.punto.", "1numero", "con espacio", ""):
        try:
            validate_username(invalid)
            raise AssertionError("it had to reject {!r}".format(invalid))
        except KutralError:
            pass


def test_splitting_the_name_leaves_the_surnames_in_sn():
    """The inherited script wrote the full name into `sn`."""
    assert split_name("Diego Muñoz Salas") == ["Diego", "Muñoz Salas"]
    assert split_name("Madonna") == ["Madonna", "Madonna"]


def test_suggesting_a_username_strips_the_accents_and_avoids_collisions():
    assert suggest_username("Diego Muñoz") == "dmunoz"
    assert suggest_username("Iván Prado") == "iprado"
    assert suggest_username("Diego Muñoz", taken=["dmunoz"]) == "dmunoz2"


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def test_creating_a_user_completes_the_chain(tmp_path):
    env = _env(tmp_path, send_mail="always", hooks=["sh agrega_storage.sh {password_file}"])
    result = creation.create_user(env, _data())

    entry = env.directory.get_user("dmunozs")
    assert entry["cn"] == "Diego Muñoz Salas"
    assert entry["sn"] == "Muñoz Salas", "the surnames, not the full name"
    assert entry["givenName"] == "Diego"
    # `gecos` goes without accents **on purpose**: the directory defines it with ASCII
    # syntax and rejects the creation with `invalidAttributeSyntax`. The real name, with
    # its accents, goes in `cn`, `displayName` and `sn`, which do accept UTF-8.
    assert entry["gecos"] == "Diego Munoz Salas"
    assert entry["displayName"] == "Diego Muñoz Salas"
    assert entry["userPassword"].startswith("{CRYPT}$6$")
    assert result["password"] not in entry["userPassword"], "it must not be left in the clear"
    assert entry["homeDirectory"].endswith("dmunozs")
    assert entry["employeeType"] == "student" and entry["o"] == "UOH"
    assert entry["departmentNumber"] == "lab-06"

    # memberUid from the start
    assert "dmunozs" in (env.directory.get_group("lab-06").get("memberUid") or [])
    # storage: really created in the sandbox
    assert os.path.isdir(env.storage.home("dmunozs"))
    assert env.storage.ownership_of(env.storage.home("dmunozs"))["mode"] == 0o750
    # Slurm
    assert env.slurm.associations("dmunozs") == ["lab-06"]
    # mail with the temporary password
    assert env.mailer.kinds() == ["welcome"]
    assert env.mailer.last()["context"]["temp_pass"] == result["password"]
    # hooks
    assert env.hooks.names() == ["after_create"]
    context = env.hooks.calls[0]["context"]
    assert context["username"] == "dmunozs"
    assert context["group"] == "lab-06"
    assert context["password"] == result["password"]


def test_the_uid_comes_from_the_highest_one_in_use(tmp_path):
    env = _env(tmp_path)
    result = creation.create_user(env, _data())
    assert result["uid"] == 1272, "the real maximum is 1271"
    assert result["gid"] == 9000, "the gid of the lab-06 group"


def test_uid_gaps_are_not_reused(tmp_path):
    """A freed uid may still own orphan files."""
    env = _env(tmp_path)
    first = creation.create_user(env, _data(username="usuario01"))
    second = creation.create_user(env, _data(username="usuario02", mail="b@ejemplo.cl"))
    assert second["uid"] == first["uid"] + 1


def test_a_repeated_user_fails_before_touching_anything(tmp_path):
    env = _env(tmp_path)
    creation.create_user(env, _data())
    actions = list(env.directory.actions())
    try:
        creation.create_user(env, _data(mail="otro@ejemplo.cl"))
        raise AssertionError("it had to fail")
    except EntryExists:
        pass
    assert env.directory.actions() == actions, "nothing may have been written"


def test_a_missing_group_warns_before_creating(tmp_path):
    env = _env(tmp_path)
    try:
        creation.create_user(env, _data(group="lab-que-no-existe"))
        raise AssertionError("it had to fail")
    except EntryNotFound as exc:
        assert "grupo" in str(exc).lower()
    assert env.directory.actions() == []


def test_the_username_is_normalised_to_lowercase():
    """Typing 'DMunoz' is not an error: it is normalised to 'dmunoz'.

    That is more useful than rejecting it — the operator types the name however it comes
    out, and the account always ends up lowercase, which is what the directory uses.
    """
    assert validate_username("DMunoz") == "dmunoz"
    assert validate_username("  IPrado  ") == "iprado"


def test_the_previous_validations_stop_the_creation(tmp_path):
    env = _env(tmp_path)
    for payload in (_data(mail="sin-arroba"), _data(username="con..punto"),
                    _data(fullname="  "), _data(username="a" * 12), _data(uid="no-numero")):
        try:
            creation.create_user(env, payload)
            raise AssertionError("it had to reject {!r}".format(payload))
        except KutralError:
            pass
    assert env.directory.actions() == []


def test_creating_with_an_expiry_date(tmp_path):
    env = _env(tmp_path)
    creation.create_user(env, _data(), expires=datetime.date(2027, 1, 1))
    entry = env.directory.get_user("dmunozs")
    assert entry["shadowExpire"] == "20819"
    assert accounts.is_expiring(entry)


def test_creating_without_a_date_stays_permanent_with_an_explicit_marker(tmp_path):
    """Option B: `-1` is written explicitly, like the 136 active accounts in the directory.

    Leaving the attribute absent also means "no expiry" for PAM, but then the new account
    would read differently from most of the directory.
    """
    env = _env(tmp_path)
    creation.create_user(env, _data())
    entry = env.directory.get_user("dmunozs")
    assert entry["shadowExpire"] == "-1"
    assert accounts.is_active(entry)
    assert not accounts.is_expiring(entry)


def test_creating_without_a_date_can_leave_the_attribute_absent(tmp_path):
    """The inherited behaviour is still available from the configuration."""
    config = _config(str(tmp_path))
    config["cluster"]["permanent_marker"] = "ausente"
    env = build_environment(config)
    creation.create_user(env, _data())
    entry = env.directory.get_user("dmunozs")
    assert "shadowExpire" not in entry
    assert accounts.is_active(entry)


def test_the_audit_log_does_not_keep_the_password(tmp_path):
    env = _env(tmp_path)
    env.auditor = AuditLog(_config(str(tmp_path)))
    result = creation.create_user(env, _data())

    folder = os.path.join(str(tmp_path), "sandbox", "logs")
    files = [f for f in os.listdir(folder) if f.endswith(".jsonl")]
    contents = open(os.path.join(folder, files[0]), encoding="utf-8").read()
    assert result["password"] not in contents, "the password cannot stay in the log"
    assert "REDACTADO" in contents
    line = json.loads(contents.strip().splitlines()[0])
    assert line["action"] == "create-user" and line["target"] == "dmunozs"


def test_a_failing_hook_is_warned_about_in_the_result(tmp_path):
    """The Nextcloud space (or another hook) may be left undone: that has to be visible.

    Before, a failing hook only showed up in `--json` and in the audit log: the console
    said "Usuario 'x' creado" and nobody found out that the mount was never made.
    """
    env = _env(tmp_path)
    env.hooks.run = lambda *a, **k: [{"command": "nextcloud_user.sh pnc1 labnc …",
                                      "ok": False,
                                      "stderr": "occ: command not found"}]

    result = creation.create_user(env, _data())

    assert result["warnings"] == [[
        "El hook falló: nextcloud_user.sh pnc1 labnc … (occ: command not found)."]]


def test_the_simulation_creates_nothing_sends_nothing_and_runs_no_hooks(tmp_path):
    env = _env(tmp_path, send_mail="always", hooks=["sh algo.sh {username}"])
    env.dry_run = True
    result = creation.create_user(env, _data())

    assert result["username"] == "dmunozs" and result["password"]
    assert env.directory.get_user("dmunozs") is None
    assert env.directory.actions() == []
    assert env.slurm.calls == []
    assert env.mailer.calls == []
    assert env.hooks.calls == []
    assert not os.path.isdir(env.storage.home("dmunozs"))


def test_without_mail_nothing_is_sent(tmp_path):
    env = _env(tmp_path, send_mail="ask")
    result = creation.create_user(env, _data())
    assert result["mail_sent"] is False
    assert result["pending_confirmation"] is True


# ---------------------------------------------------------------------------
# Consultation
# ---------------------------------------------------------------------------

def test_the_consultation_joins_the_four_sources(tmp_path):
    env = _env(tmp_path)
    uid = env.directory.list_users()[1]["uid"]
    env.slurm.users[uid] = ["lab-06"]
    # It simulates the copy in this host's /etc/passwd, which is the real case.
    env.identity.local_accounts.add(uid)

    snapshot = consultation.user_snapshot(env, uid)

    assert snapshot["exists"] is True
    assert snapshot["primary_group"]
    assert snapshot["slurm_accounts"] == ["lab-06"]
    assert snapshot["home"].endswith(uid)
    assert snapshot["local_account"] is True


def test_the_consultation_warns_about_the_local_account(tmp_path):
    """It is the warning that explains why an LDAP change 'is not seen'."""
    env = _env(tmp_path)
    uid = env.directory.list_users()[1]["uid"]
    env.identity.local_accounts.add(uid)
    warnings = consultation.warnings_for(consultation.user_snapshot(env, uid))
    assert any("LOCAL" in warning for warning in warnings)
    assert any("files" in warning for warning in warnings)


def test_consulting_a_missing_account_says_so(tmp_path):
    env = _env(tmp_path)
    snapshot = consultation.user_snapshot(env, "nadie")
    assert snapshot["exists"] is False
    assert "no se encontr" in consultation.render_snapshot(snapshot).lower()
    assert consultation.warnings_for(snapshot)


def test_the_consultation_sees_the_freshly_created_home(tmp_path):
    """In dry-run mode the configured paths are relative.

    The consultation cannot report a false "el home no existe": a false warning makes the
    operator stop believing the warnings.
    """
    env = _env(tmp_path)
    creation.create_user(env, _data())
    snapshot = consultation.user_snapshot(env, "dmunozs")
    assert snapshot["home_exists"] is True
    assert not any("home no existe" in warning
                   for warning in consultation.warnings_for(snapshot))


def test_the_consultation_renders_without_failing(tmp_path):
    env = _env(tmp_path)
    uid = env.directory.list_users()[0]["uid"]
    text = consultation.render_snapshot(consultation.user_snapshot(env, uid))
    assert uid in text
    assert "Estado" in text and "Grupo primario" in text
    assert "departmentNumber" in text


def test_the_consultation_shows_the_missing_label(tmp_path):
    """There are real entries without `departmentNumber`.

    Showing the primary group (which comes from the gidNumber) as if it were the label
    hides exactly the gap the consultation should expose.
    """
    env = _env(tmp_path)
    without_label = [u for u in env.directory.list_users() if not u.get("departmentNumber")]
    assert without_label, "the seed has entries without departmentNumber"
    text = consultation.render_snapshot(
        consultation.user_snapshot(env, without_label[0]["uid"]))
    assert "(ausente)" in text


def test_finding_users_by_several_criteria(tmp_path):
    env = _env(tmp_path)
    some = env.directory.list_users()[0]
    assert consultation.find_users(env, some["uid"])
    assert consultation.find_users(env, str(some["cn"]).split()[0])
    assert consultation.find_users(env, str(some["mail"]).split("@")[0])


def test_the_summary_counts_by_state(tmp_path):
    env = _env(tmp_path)
    summary = consultation.summary(env)
    assert summary["users"] == 214 and summary["groups"] == 53
    assert sum(summary["by_state"].values()) == 214
    assert summary["next_uid"] == 1272
    assert summary["without_group_label"] > 0
    assert summary["environment"] == "lab"
