#!/usr/bin/env python3
"""Kutral Control Center — command line.

    python3 kutral_mgr.py status
    python3 kutral_mgr.py consult iprado
    python3 kutral_mgr.py --simulate deactivate iprado --reason "fin de curso"
    python3 kutral_mgr.py --config config.lab.yaml --yes create-user \
        --full-name "Diego Muñoz" --username dmunoz --group lab-06 --mail a@ejemplo.cl

The tool is bilingual: every command and flag has its English name and its Spanish
name, and the messages come from the catalog in `common/messages.py`.

    python3 kutral_mgr.py --lang en consult iprado
    python3 kutral_mgr.py consultar iprado --idioma es

Global flags:

    --config    configuration file (config.yaml by default)
    --simulate  walk the whole flow without writing anything and without mail
    --json      JSON output, for automation
    --yes       ask nothing: use only what came as a parameter
    --enviar-correo / --no-enviar-correo   force mail on or off
    --sin-cabecera                        do not print the environment header
    --lang es|en                          language of the messages

(The global mail flag is deliberately NOT called `--mail`: `create-user` and
`modify-user` use `--mail` for the person's address, and two options with the same
name in the same parser make argparse fail to build it.)

They can go before or after the subcommand.

Against the real cluster **every** command works: the five adapters —LDAP, Slurm,
identity, storage and mail— are real. And with `--config config.lab.yaml` they run
against an in-memory directory and an on-disk sandbox, to rehearse any flow without
touching the cluster.

Design note: the domain imports are **inside** `main()`. That way this file can be
imported without `ldap3` or `PyYAML` installed —`--help` still answers— and the
parser can be tested in isolation from the rest.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from modules.common import i18n  # noqa: E402
from modules.common.i18n import t  # noqa: E402

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_CANCELADO = 130

#: Defaults of the global flags. They are applied in the main parser, not in the
#: shared one: see `build_parser`.
DEFAULT_GLOBALS = {"config": "config.yaml", "simulate": False, "as_json": False,
                   "yes": False, "enviar_correo": None, "sin_cabecera": False,
                   "lang": None}

#: Spanish names for the commands. Both spellings build the same handler: the
#: operator should be able to work in his own language without learning English.
ALIASES = {
    "status": "estado",
    "consult": "consultar",
    "export": "exportar",
    "verify": "verificar",
    "gen-password": "generar-clave",
    "create-user": "crear-usuario",
    "modify-user": "modificar-usuario",
    "change-group": "cambiar-grupo",
    "add-member": "agregar-miembro",
    "remove-member": "quitar-miembro",
    "rename-user": "renombrar-usuario",
    "deactivate": "desactivar",
    "reactivate": "reactivar",
    "reset-password": "resetear-clave",
    "expire-set": "fijar-vencimiento",
    "delete-user": "borrar-usuario",
    "group-create": "crear-grupo",
    "group-show": "mostrar-grupo",
    "group-add-member": "agregar-miembros",
    "group-remove-member": "quitar-miembros",
    "group-delete": "borrar-grupo",
}


def _shared_flags() -> argparse.ArgumentParser:
    """Global flags, so they work before **and** after the subcommand.

    Two details that were expensive to find and should not be undone:

    1. They carry `default=argparse.SUPPRESS`: that way no parser writes a value the
       operator did not ask for.
    2. **`set_defaults` must not be applied to them in the main parser.**
       `parents=[...]` shares the *same* `Action` objects between the main parser and
       each subparser, and `set_defaults` rewrites `action.default`. Result: the
       subparser kept its own `default` and overwrote the value already read.
       Measured on Python 3.14: `kutral_mgr --simulate status` ended up with
       `simulate=False`, silently.

    The defaults are filled in after parsing, in `parse()`.

    Every flag has its Spanish name too (`--simular`, `--si`, `--salida-json`…).
    """
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--config", default=argparse.SUPPRESS, help=t("flag.config"))
    comun.add_argument("--simulate", "--simular", action="store_true", dest="simulate",
                       default=argparse.SUPPRESS, help=t("flag.simulate"))
    comun.add_argument("--json", "--salida-json", action="store_true", dest="as_json",
                       default=argparse.SUPPRESS, help=t("flag.json"))
    comun.add_argument("--yes", "--si", "--sí", action="store_true", default=argparse.SUPPRESS,
                       help=t("flag.yes"))
    comun.add_argument("--enviar-correo", "--send-mail", dest="enviar_correo",
                       action="store_true", default=argparse.SUPPRESS,
                       help=t("flag.send_mail"))
    comun.add_argument("--no-enviar-correo", "--no-send-mail", dest="enviar_correo",
                       action="store_false", default=argparse.SUPPRESS,
                       help=t("flag.no_send_mail"))
    comun.add_argument("--sin-cabecera", "--no-header", dest="sin_cabecera",
                       action="store_true", default=argparse.SUPPRESS,
                       help=t("flag.no_header"))
    comun.add_argument("--lang", "--idioma", dest="lang",
                       default=argparse.SUPPRESS, help=t("flag.lang"))
    return comun


def build_parser() -> argparse.ArgumentParser:
    """Build the parser. It imports nothing from the domain: only command names."""
    shared = _shared_flags()
    parser = argparse.ArgumentParser(
        prog="kutral_mgr",
        description=t("parser.description"),
        parents=[shared])
    # No `set_defaults` here: see the note in `_shared_flags`.
    sub = parser.add_subparsers(dest="command")

    def add(name: str, help_key: str):
        p = sub.add_parser(name, help=t(help_key), aliases=[ALIASES[name]],
                           parents=[shared])
        p.set_defaults(handler_name=name)
        return p

    add("status", "help.cmd.status")

    p = add("consult", "help.cmd.consult")
    p.add_argument("term", nargs="?", default="", help=t("help.arg.term"))

    p = add("export", "help.cmd.export")
    p.add_argument("--output", "--salida", help=t("flag.output"))

    add("verify", "help.cmd.verify")

    p = add("gen-password", "help.cmd.gen_password")
    p.add_argument("--length", "--largo", type=int, default=0, help=t("flag.length"))

    p = add("create-user", "help.cmd.create_user")
    p.add_argument("--full-name", "--nombre-completo", dest="full_name",
                   help=t("flag.full_name"))
    p.add_argument("--username", "--usuario", help=t("flag.username"))
    p.add_argument("--group", "--grupo", help=t("flag.group"))
    p.add_argument("--mail", "--correo", help=t("flag.mail"))
    p.add_argument("--employee-type", "--tipo-cuenta", dest="employee_type",
                   help=t("flag.employee_type"))
    p.add_argument("--institute", "--institucion", "--institución", dest="institute",
                   help=t("flag.institute"))
    p.add_argument("--course", "--curso", help=t("flag.course"))
    p.add_argument("--expires", "--vence", help=t("flag.expires"))

    p = add("modify-user", "help.cmd.modify_user")
    p.add_argument("username")
    p.add_argument("--full-name", "--nombre-completo", dest="full_name",
                   help=t("flag.full_name"))
    p.add_argument("--mail", "--correo", help=t("flag.mail"))
    p.add_argument("--shell", help=t("flag.shell"))
    p.add_argument("--employee-type", "--tipo-cuenta", dest="employee_type",
                   help=t("flag.employee_type"))
    p.add_argument("--institute", "--institucion", "--institución", dest="institute",
                   help=t("flag.institute"))
    p.add_argument("--course", "--curso", help=t("flag.course"))
    p.add_argument("--group", "--grupo", help=t("help.cmd.change_group"))
    p.add_argument("--keep-old", "--conservar-grupo", action="store_true", dest="keep_old",
                   help=t("flag.keep_old"))

    p = add("change-group", "help.cmd.change_group")
    p.add_argument("username")
    p.add_argument("group")
    p.add_argument("--keep-old", "--conservar-grupo", action="store_true", dest="keep_old",
                   help=t("flag.keep_old"))

    p = add("add-member", "help.cmd.add_member")
    p.add_argument("username")
    p.add_argument("group")

    p = add("remove-member", "help.cmd.remove_member")
    p.add_argument("username")
    p.add_argument("group")

    p = add("rename-user", "help.cmd.rename_user")
    p.add_argument("username")
    p.add_argument("new_username")
    p.add_argument("--keep-home", "--conservar-home", action="store_true", dest="keep_home",
                   help=t("flag.keep_home"))

    p = add("deactivate", "help.cmd.deactivate")
    p.add_argument("username")
    p.add_argument("--reason", "--motivo", help=t("flag.reason"))
    p.add_argument("--keep-slurm", "--conservar-slurm", action="store_true", dest="keep_slurm",
                   help=t("flag.keep_slurm"))

    p = add("reactivate", "help.cmd.reactivate")
    p.add_argument("username")
    p.add_argument("--expires", "--vence", help=t("flag.expires"))
    p.add_argument("--keep-password", "--conservar-clave", action="store_true",
                   dest="keep_password", help=t("flag.keep_password"))

    p = add("reset-password", "help.cmd.reset_password")
    p.add_argument("username")

    p = add("expire-set", "help.cmd.expire_set")
    p.add_argument("expires", help=t("flag.expire_set.value"))
    p.add_argument("usernames", nargs="*", help=t("flag.expire_set.usernames"))
    p.add_argument("--file", "--archivo", help=t("flag.expire_set.file"))

    p = add("delete-user", "help.cmd.delete_user")
    p.add_argument("username")
    p.add_argument("--archive-home", "--archivar-home", action="store_true",
                   dest="archive_home", help=t("flag.archive_home"))
    p.add_argument("--delete-home", "--borrar-home", action="store_true",
                   dest="delete_home", help=t("flag.delete_home"))
    p.add_argument("--keep-slurm", "--conservar-slurm", action="store_true", dest="keep_slurm",
                   help=t("flag.keep_slurm"))

    p = add("group-create", "help.cmd.group_create")
    p.add_argument("name")
    p.add_argument("--gid", type=int)
    p.add_argument("--members", "--miembros", help=t("flag.members"))
    p.add_argument("--no-lab", "--sin-laboratorio", action="store_true", dest="no_lab",
                   help=t("flag.no_lab"))

    p = add("group-show", "help.cmd.group_show")
    p.add_argument("group")

    p = add("group-add-member", "help.cmd.group_add_member")
    p.add_argument("group")
    p.add_argument("usernames", nargs="+", help=t("flag.usernames"))

    p = add("group-remove-member", "help.cmd.group_remove_member")
    p.add_argument("group")
    p.add_argument("usernames", nargs="+", help=t("flag.usernames"))
    p.add_argument("--drop-slurm", "--quitar-slurm", action="store_true", dest="drop_slurm",
                   help=t("flag.drop_slurm"))

    p = add("group-delete", "help.cmd.group_delete")
    p.add_argument("group")
    p.add_argument("--force", "--forzar", action="store_true", help=t("flag.force"))
    p.add_argument("--remove-lab", "--borrar-laboratorio", action="store_true",
                   dest="remove_lab", help=t("flag.remove_lab"))

    return parser


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def parse(argv=None, parser: argparse.ArgumentParser = None) -> argparse.Namespace:
    """Parse the arguments and fill in the defaults of the global flags.

    This is the only way the arguments should be parsed: calling `parse_args`
    directly leaves the global flags the operator did not use as missing attributes
    (they carry SUPPRESS) and any `args.config` would fail.
    """
    parser = parser or build_parser()
    args = parser.parse_args(argv)
    for key, value in DEFAULT_GLOBALS.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    if args.lang:
        i18n.set_language(args.lang)
    return args


def _ask_password_if_missing(config: dict) -> None:
    """With `--yes`, ask **only** for the directory password if there is no other source.

    `--yes` means "ask nothing", but without a credential no operation is possible:
    on a terminal the operator has it at hand, so it is asked once and left in the
    session's environment variable —the mechanism the runbook already documents—.
    In a script or a cron there is no terminal: there it fails, which is the correct
    behaviour, so that nobody is left waiting for an answer that will not come.
    """
    ldap = config.get("ldap") or {}
    env_name = ldap.get("password_env") or "KUTRAL_LDAP_PASSWORD"
    if os.environ.get(env_name):
        return
    path = ldap.get("password_file")
    if path and os.path.exists(str(path)):
        return
    try:
        if not sys.stdin.isatty():
            return
    except Exception:              # stdin closed or replaced
        return
    import getpass
    secret = getpass.getpass(t("cli.password.prompt"))
    if secret:
        os.environ[env_name] = secret


def print_header(config: dict, environment, sin_cabecera: bool = False) -> None:
    """One-line header: against what, and in which mode, the operator is working.

    It used to be three framed lines, and with 20 commands in a row that is noise.
    With `--sin-cabecera` it does not silence everything: the simulation notice is
    still printed, because that is the difference between "this writes nothing" and a
    real change in the directory.
    """
    simulated = bool(getattr(environment, "dry_run", False))
    if sin_cabecera:
        if simulated:
            print(t("cli.mode.simulated.notice"))
        return
    parts = [
        t("cli.header.env", value=config.get("environment")),
        t("cli.header.ldap", value=config["ldap"]["server"]),
        t("cli.header.mode",
          value=t("cli.mode.simulated") if simulated else t("cli.mode.real")),
    ]
    # "correo: se pregunta" would be noise: the command itself asks when it applies.
    if getattr(environment, "mail_policy", "ask") != "ask":
        parts.append(t("cli.header.mail", value=environment.mail_policy))
    print(" | ".join(parts))


def print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return
    for block in result.get("rendered") or []:
        print(block)
    for warnings in result.get("warnings") or []:
        for warning in warnings:
            print("[!] {}".format(warning))
    if result.get("message"):
        print(result["message"])
    if result.get("password"):
        # In simulation nobody has that password: printing it bare invites copying it
        # and handing it over as if it existed.
        suffix = (t("cli.result.password.simulated") if result.get("dry_run") else "")
        print(t("cli.result.password", value=result["password"], suffix=suffix))
    if result.get("path"):
        print(t("cli.result.path", value=result["path"]))
    if result.get("uid") is not None and result.get("gid") is not None:
        print(t("cli.result.ids", uid=result["uid"], gid=result["gid"]))


def _error(message: str, as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, indent=2, ensure_ascii=False))
    else:
        print(t("cli.error.prefix", message=message), file=sys.stderr)
    return code


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # The help texts have to be built in one language, so the language is resolved
    # before the parser exists (the flag may appear anywhere, hence the pre-scan).
    i18n.set_language(i18n.detect(explicit=i18n.from_argv(arguments)))
    parser = build_parser()
    args = parse(arguments, parser)
    if not getattr(args, "handler_name", None):
        parser.print_help()
        return SALIDA_OK

    # Domain imports, only here: the parser and --help do not need them.
    from modules.cli import commands
    from modules.cli.environment import build_environment, persist_lab_state
    from modules.common.errors import KutralError, OperationCancelled
    from modules.core import config as cfgmod

    try:
        config = cfgmod.load_config(args.config)
    except KutralError as exc:
        return _error(str(exc), args.as_json, SALIDA_ERROR)

    if args.yes:
        _ask_password_if_missing(config)

    try:
        environment = build_environment(config, simulate=bool(args.simulate),
                                        interactive=not args.yes)
    except KutralError as exc:
        return _error(str(exc), args.as_json, SALIDA_ERROR)

    try:
        if not args.as_json:
            print_header(config, environment, sin_cabecera=bool(args.sin_cabecera))
        result = commands.HANDLERS[args.handler_name](environment, args)
        result.setdefault("ok", True)
        result.setdefault("dry_run", bool(args.simulate))
        print_result(result, args.as_json)
    except OperationCancelled as exc:
        return _error(t("cli.error.cancelled", message=exc), args.as_json, SALIDA_CANCELADO)
    except KeyboardInterrupt:
        return _error(t("cli.error.interrupted"), args.as_json, SALIDA_CANCELADO)
    except KutralError as exc:
        return _error(str(exc), args.as_json, SALIDA_ERROR)
    finally:
        persist_lab_state(environment, guardar=not args.simulate)
    return SALIDA_OK


if __name__ == "__main__":
    sys.exit(main())
