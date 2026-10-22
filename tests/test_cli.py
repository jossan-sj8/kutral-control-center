"""The command line end to end, in rehearsal mode.

These tests run `kutral_mgr.main()` for real, with a real configuration file and the fake
directory persisted on disk. They cover what cannot be covered any other way:

  - that the global flags work **before and after** the subcommand (the classic
    `argparse` mistake with `parents`, where the subparser overwrites the value already
    read);
  - that the rehearsal state survives between commands, so that an account can be created
    and then queried;
  - that `--simulate` leaves no trace;
  - that errors come out through the right exit code and, with `--json`, as JSON.
"""

from __future__ import annotations

import contextlib
import io
import json
import os

import kutral_mgr


TEMPLATE = """environment: lab
ldap:
  server: "ldap://10.20.0.10"
  base_dn: "ou=People,<SUFIJO_DEL_DIRECTORIO>"
  group_dn: "ou=Group,<SUFIJO_DEL_DIRECTORIO>"
  root_dn: "<SUFIJO_DEL_DIRECTORIO>"
  manager_dn: "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>"
paths:
  beegfs_home: "{base}/home"
  beegfs_labs: "{base}/labs"
  beegfs_history: "{base}/history"
  logs_dir: "{base}/logs"
  backups_dir: "{base}/backups"
  mail_dir: "{base}/mail"
  state_file: "{base}/directory.json"
  tutorial_pdf: "no-existe.pdf"
smtp:
  transport: file
  sender: "hpc@ejemplo.cl"
  server: "localhost"
  port: 25
cluster:
  name: "Kutral HPC (LAB)"
  login_host: "198.51.100.104"
  default_shell: "/bin/bash"
  nologin_shell: "/sbin/nologin"
  default_gid: 9000
  uid_start: 1150
  shadow_expire_permanent: -1
  password_scheme: "{{CRYPT}}"
  password_length: 12
  send_mail: "never"
slurm:
  enabled: true
  fallback_account: "hpc-default"
  capture_associations: true
hooks:
  after_create: []
  after_delete: []
  after_group_create: []
guard_networks:
  - "192.0.2.0/24"
"""


def _config_path(tmp_path) -> str:
    path = os.path.join(str(tmp_path), "config.lab.yaml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(TEMPLATE.format(base=str(tmp_path).replace("\\", "/")))
    return path


def _run(*arguments, tmp_path) -> tuple:
    """Run the CLI capturing output and exit code."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    arguments = [str(a) for a in arguments]
    if "--config" not in arguments:
        arguments = ["--config", _config_path(tmp_path)] + arguments
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kutral_mgr.main(arguments)
    except SystemExit as exc:      # this is how argparse exits
        code = int(exc.code or 0)
    return code, out.getvalue(), err.getvalue()


def _json(output: str) -> dict:
    return json.loads(output)


# ---------------------------------------------------------------------------
# Global flags (the classic argparse mistake with parents)
# ---------------------------------------------------------------------------

def test_the_global_flags_work_in_both_positions():
    """The case that used to break: `parents=[...]` shares the Action objects, so
    `set_defaults` on the main parser left the subparser overwriting the value already
    read. Measured before the fix: `[--simulate status]` gave simulate=False."""
    before = kutral_mgr.parse(["--simulate", "--json", "deactivate", "iprado"])
    after = kutral_mgr.parse(["deactivate", "iprado", "--simulate", "--json"])

    assert before.simulate is True and before.as_json is True
    assert after.simulate is True and after.as_json is True
    assert before.handler_name == "deactivate" and after.handler_name == "deactivate"


def test_the_defaults_survive_the_subcommand():
    args = kutral_mgr.parse(["status"])
    assert args.config == "config.yaml"
    assert args.simulate is False and args.as_json is False and args.enviar_correo is None


def test_the_mail_flags_are_resolved():
    """The global one is --enviar-correo: --mail is the person's address."""
    assert kutral_mgr.parse(["--no-enviar-correo", "status"]).enviar_correo is False
    assert kutral_mgr.parse(["status", "--enviar-correo"]).enviar_correo is True
    assert kutral_mgr.parse(["status"]).enviar_correo is None
    # The person's address is still --mail, with no conflict and no clash of destinations
    # with the global flag.
    parsed = kutral_mgr.parse(["create-user", "--mail", "a@ejemplo.cl"])
    assert parsed.mail == "a@ejemplo.cl" and parsed.enviar_correo is None


def test_the_parameter_destinations_are_the_expected_ones():
    args = kutral_mgr.parse(["create-user", "--full-name", "Diego V", "--username", "dmunoz",
                             "--group", "lab-06", "--mail", "a@ejemplo.cl",
                             "--employee-type", "student", "--expires", "fin-de-anio"])
    assert args.full_name == "Diego V" and args.username == "dmunoz"
    assert args.employee_type == "student" and args.expires == "fin-de-anio"
    usernames = kutral_mgr.parse(["group-add-member", "lab-06", "uno", "dos"])
    assert usernames.usernames == ["uno", "dos"]


def test_a_missing_command_fails():
    try:
        kutral_mgr.parse(["telegrama"])
        raise AssertionError("argparse should have rejected it")
    except SystemExit as exc:
        assert exc.code == 2


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def test_status_in_json_gives_the_counts(tmp_path):
    code, output, _ = _run("status", "--json", tmp_path=tmp_path)
    assert code == 0
    data = _json(output)
    assert data["users"] == 214 and data["groups"] == 53
    assert data["environment"]["environment"] == "lab"


def test_the_header_states_the_environment_and_the_mode(tmp_path):
    code, output, _ = _run("--simulate", "status", tmp_path=tmp_path)
    assert code == 0
    assert "entorno: lab" in output and "SIMULACIÓN" in output


def test_the_header_fits_in_one_line_and_can_be_silenced(tmp_path):
    """It used to be three framed lines: with 20 commands in a row, noise.

    What is **never** silenced is the mode: it is the difference between ``this writes
    nothing`` and a real change in the directory.
    """
    code, output, _ = _run("--simulate", "status", tmp_path=tmp_path)
    assert code == 0
    assert output.splitlines()[0].startswith("entorno: lab | ldap: ldap://10.20.0.10 | modo: ")

    code, output, _ = _run("--simulate", "--sin-cabecera", "status", tmp_path=tmp_path)
    assert code == 0
    assert output.splitlines()[0] == "modo: SIMULACIÓN (no se escribe nada)"


def test_expire_set_is_a_real_command(tmp_path):
    """Parser, dispatch and output: the new command, end to end in rehearsal."""
    code, output, error = _run("--simulate", "expire-set", "nunca", "aalarcon",
                               tmp_path=tmp_path)
    assert code == 0, error
    assert "Vencimiento actualizado" in output
    assert "sin vencimiento" in output


def test_expire_set_with_no_users_fails_clearly(tmp_path):
    code, _, error = _run("expire-set", "nunca", tmp_path=tmp_path)
    assert code != 0
    assert "No hay usuarios" in error


def test_consult_finds_and_warns(tmp_path):
    code, first_output, _ = _run("status", "--json", tmp_path=tmp_path)
    uid = _json(first_output)["next_uid"]      # 1272: the next free one
    assert uid == 1272

    code, output, _ = _run("consult", "aalarcon", "--json", tmp_path=tmp_path)
    assert code == 0
    data = _json(output)
    assert data["found"] >= 1


def test_consulting_something_missing_is_not_an_error(tmp_path):
    code, output, _ = _run("consult", "zzzznoexiste", "--json", tmp_path=tmp_path)
    assert code == 0
    assert _json(output)["found"] == 0


def test_creating_and_then_consulting_the_same_user(tmp_path):
    """This is what requires the rehearsal state to be kept between commands."""
    code, output, error = _run("--yes", "--no-enviar-correo", "create-user",
                               "--full-name", "Diego Muñoz", "--username", "dmunoz",
                               "--group", "lab-06", "--mail", "dmunoz@ejemplo.cl",
                               tmp_path=tmp_path)
    assert code == 0, error
    assert "contraseña temporal" in output

    code, output, _ = _run("consult", "dmunoz", "--json", tmp_path=tmp_path)
    assert code == 0
    data = _json(output)
    assert data["found"] == 1
    assert data["snapshots"][0]["primary_group"] == "lab-06"


def test_under_simulation_no_state_is_left_behind(tmp_path):
    code, output, error = _run("--simulate", "--yes", "create-user",
                               "--full-name", "Nadie Prueba", "--username", "nadieprueba",
                               "--group", "lab-06", "--mail", "nadie@ejemplo.cl",
                               tmp_path=tmp_path)
    assert code == 0, error
    # Nobody holds the rehearsal password: if it is printed bare, somebody copies it and
    # hands it to the person as if it worked.
    assert "no se aplicó" in output
    code, output, _ = _run("consult", "nadieprueba", "--json", tmp_path=tmp_path)
    assert _json(output)["found"] == 0


def test_an_error_returns_code_1(tmp_path):
    code, _, error = _run("--yes", "create-user", "--full-name", "Prueba",
                          "--username", "prueba", "--group", "lab-06",
                          "--mail", "sin-arroba", tmp_path=tmp_path)
    assert code == 1
    assert "Correo" in error


def test_the_error_in_json_is_json(tmp_path):
    code, output, _ = _run("--yes", "--json", "create-user", "--full-name", "Prueba",
                           "--username", "prueba", "--group", "lab-06",
                           "--mail", "sin-arroba", tmp_path=tmp_path)
    assert code == 1
    data = _json(output)
    assert data["ok"] is False and "Correo" in data["error"]


def test_the_full_group_cycle(tmp_path):
    code, output, error = _run("--yes", "group-create", "labprueba",
                               "--gid", "9500", "--members", "aalarcon,bhinojosa",
                               tmp_path=tmp_path)
    assert code == 0, error
    assert "labprueba" in output

    code, output, error = _run("group-show", "labprueba", "--json", tmp_path=tmp_path)
    assert code == 0, error
    data = _json(output)
    assert data["member_count"] == 2 and data["lab_exists"] is True

    code, output, error = _run("--yes", "group-add-member", "labprueba", "coyarce",
                               tmp_path=tmp_path)
    assert code == 0, error
    code, output, _ = _run("group-show", "labprueba", "--json", tmp_path=tmp_path)
    assert _json(output)["member_count"] == 3


def test_a_group_with_members_is_not_deleted(tmp_path):
    _run("--yes", "group-create", "labprueba", "--gid", "9500",
         "--members", "aalarcon", tmp_path=tmp_path)
    code, _, error = _run("--yes", "group-delete", "labprueba", tmp_path=tmp_path)
    assert code == 1
    assert "miembros" in error


def test_deactivating_and_reactivating(tmp_path):
    """The account is created first, on purpose.

    The first users of the seed are **blocked** (the `position < BLOCKED_USERS`
    parameter), so using one of them would make `deactivate` do nothing —rightly so— and
    the test would measure the wrong case.
    """
    code, _, error = _run("--yes", "create-user",
                          "--full-name", "Prueba Desactivar", "--username", "pdesact",
                          "--group", "lab-06", "--mail", "pdesact@ejemplo.cl",
                          tmp_path=tmp_path)
    assert code == 0, error

    code, output, error = _run("--yes", "deactivate", "pdesact",
                               "--reason", "fin de curso", tmp_path=tmp_path)
    assert code == 0, error
    assert "desactivado" in output

    code, output, error = _run("--yes", "reactivate", "pdesact",
                               "--expires", "fin-de-anio", tmp_path=tmp_path)
    assert code == 0, error
    assert "contraseña temporal" in output and "2027-01-01" in output
    # And it has to say which Slurm account it went back to: it used not to, and if the
    # backup had been lost the account stayed in hpc-default without anybody knowing.
    assert "Slurm: lab-06" in output


def test_export_writes_the_excel_file(tmp_path):
    code, output, error = _run("export", "--json", tmp_path=tmp_path)
    assert code == 0, error
    data = _json(output)
    assert os.path.exists(data["path"])
    assert data["sheets"]["all"] == 214
    assert data["sheets"]["blocked"] == 62


def test_gen_password_does_not_need_a_directory(tmp_path):
    code, output, _ = _run("gen-password", "--length", "16", "--json", tmp_path=tmp_path)
    assert code == 0
    assert len(_json(output)["password"]) == 16


def test_the_simulation_does_not_claim_slurm_was_left_alone():
    """In simulation the writes are skipped entirely, so `slurm_removed` stays False even
    though a real `deactivate` **would** remove the associations.

    Measured against the cluster on 2026-10-08: `--simulate deactivate atest` answered
    "Slurm: no changes" about an account that does have a Slurm account.
    """
    from modules.cli import commands

    result = {"changes": ["loginShell", "shadowExpire"],
              "slurm_before": ["lab-07"], "slurm_removed": False}
    assert "lab-07" in commands._slurm_state(result, dry_run=True)
    assert commands._slurm_state({"slurm_before": [], "slurm_removed": False},
                                 dry_run=True) == "sin asociaciones que quitar"
    # Outside simulation it reports what really happened, not what is assumed.
    assert commands._slurm_state(result, dry_run=False) == "sin cambios"
    assert commands._slurm_state(dict(result, slurm_removed=True),
                                 dry_run=False) == "quitado"


def test_verify_shows_the_adapters_as_text(tmp_path):
    """The adapter list is the point of `verify`: it cannot appear only in `--json`."""
    code, output, error = _run("verify", tmp_path=tmp_path)
    assert code == 0, error
    assert "Adaptadores:" in output
    assert "slurm" in output
