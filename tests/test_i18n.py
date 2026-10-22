"""Bilingual catalog, flags in both languages and language selection.

What is tested here:

- that the catalog carries both texts of every message (a half-filled entry is a message
  that shows up in the wrong language);
- the order in which the language is chosen (flag -> variable -> locale -> Spanish);
- that the flag is read **before** the parser is built, wherever it appears;
- that every flag and every command can be written in English or in Spanish.
"""

from __future__ import annotations

import pytest

import kutral_mgr
from modules.common import i18n
from modules.common.messages import MESSAGES


def test_the_catalog_has_both_languages():
    missing = [(key, language) for key, texts in MESSAGES.items()
               for language in i18n.LANGUAGES if not (texts.get(language) or "").strip()]
    assert not missing, "messages without text: {}".format(missing)


def test_an_unknown_language_does_not_change_the_current_one():
    i18n.set_language("es")
    assert i18n.set_language("klingon") == "es"
    assert i18n.set_language(None) == "es"
    i18n.set_language("en")
    assert i18n.set_language("klingon") == "en"
    i18n.set_language("es")


def test_the_language_comes_from_the_flag_then_the_variable_then_the_locale():
    assert i18n.detect(explicit="en", environ={"KUTRAL_LANG": "es"}) == "en"
    assert i18n.detect(explicit=None, environ={"KUTRAL_LANG": "en", "LANG": "es_CL.UTF-8"}) == "en"
    assert i18n.detect(explicit=None, environ={"LANG": "en_US.UTF-8"}) == "en"
    assert i18n.detect(explicit=None, environ={"LC_ALL": "es_ES.UTF-8"}) == "es"
    assert i18n.detect(explicit=None, environ={"LANG": "C"}) == i18n.DEFAULT_LANGUAGE
    assert i18n.detect(explicit=None, environ={}) == i18n.DEFAULT_LANGUAGE


def test_the_language_flag_is_read_in_any_position():
    assert i18n.from_argv(["--lang", "en", "status"]) == "en"
    assert i18n.from_argv(["status", "--lang=en"]) == "en"
    assert i18n.from_argv(["estado", "--idioma", "ES"]) == "es"
    assert i18n.from_argv(["--idioma=es_CL", "estado"]) == "es"
    assert i18n.from_argv(["status"]) is None
    assert i18n.from_argv(["--lang"]) is None


def test_a_message_renders_in_both_languages():
    i18n.set_language("es")
    assert "contraseña temporal" in i18n.t("cli.result.password", value="x", suffix="")
    i18n.set_language("en")
    assert "temporary password" in i18n.t("cli.result.password", value="x", suffix="")
    i18n.set_language("es")


def test_an_undefined_message_is_an_error_and_not_a_silence():
    with pytest.raises(KeyError):
        i18n.t("no.existe")


def test_the_creation_flags_in_english_and_in_spanish_are_the_same():
    english = kutral_mgr.parse(["create-user", "--full-name", "Ana Prado",
                                "--username", "aprado", "--group", "lab-uno",
                                "--mail", "a@ejemplo.cl", "--employee-type", "student"])
    spanish = kutral_mgr.parse(["crear-usuario", "--nombre-completo", "Ana Prado",
                                "--usuario", "aprado", "--grupo", "lab-uno",
                                "--correo", "a@ejemplo.cl", "--tipo-cuenta", "student"])
    for field in ("full_name", "username", "group", "mail", "employee_type"):
        assert getattr(english, field) == getattr(spanish, field), field
    assert english.handler_name == spanish.handler_name == "create-user"


def test_the_global_flags_in_english_and_in_spanish_are_the_same():
    english = kutral_mgr.parse(["--simulate", "--json", "--yes", "--no-header",
                                "--no-send-mail", "status"])
    spanish = kutral_mgr.parse(["--simular", "--salida-json", "--si", "--sin-cabecera",
                                "--no-enviar-correo", "estado"])
    assert english.simulate and spanish.simulate
    assert english.as_json and spanish.as_json
    assert english.yes and spanish.yes
    assert english.sin_cabecera and spanish.sin_cabecera
    assert english.enviar_correo is False and spanish.enviar_correo is False
    assert english.handler_name == spanish.handler_name == "status"


def test_the_flag_language_is_applied_when_parsing():
    kutral_mgr.parse(["--lang", "en", "status"])
    assert i18n.language() == "en"
    kutral_mgr.parse(["--idioma", "es", "estado"])
    assert i18n.language() == "es"


def test_the_commands_are_in_both_lists():
    """The aliases are the other language of the same command: none of them may be missing."""
    assert set(kutral_mgr.ALIASES) == {
        "status", "consult", "export", "verify", "gen-password", "create-user",
        "modify-user", "change-group", "add-member", "remove-member", "rename-user",
        "deactivate", "reactivate", "reset-password", "expire-set", "delete-user",
        "group-create", "group-show", "group-add-member", "group-remove-member",
        "group-delete"}
    assert len(set(kutral_mgr.ALIASES.values())) == len(kutral_mgr.ALIASES), "repeated alias"


def test_the_help_is_built_in_both_languages():
    i18n.set_language("es")
    assert "resumen del directorio" in kutral_mgr.build_parser().format_help()
    i18n.set_language("en")
    assert "summary of the directory" in kutral_mgr.build_parser().format_help()
    i18n.set_language("es")


def test_the_header_comes_out_in_the_chosen_language(capsys):
    class Environment:
        dry_run = True
        mail_policy = "never"

    config = {"environment": "lab", "ldap": {"server": "ldap://192.0.2.154"}}
    i18n.set_language("es")
    kutral_mgr.print_header(config, Environment())
    assert capsys.readouterr().out.strip() == (
        "entorno: lab | ldap: ldap://192.0.2.154 | modo: SIMULACIÓN (no se escribe nada)"
        " | correo: never")
    i18n.set_language("en")
    kutral_mgr.print_header(config, Environment())
    assert capsys.readouterr().out.strip() == (
        "environment: lab | ldap: ldap://192.0.2.154 | mode: SIMULATION (nothing is written)"
        " | mail: never")
    i18n.set_language("es")
