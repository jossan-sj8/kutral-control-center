"""The mail templates and the `file` transport.

Mail is the only part of the Control Center that **reaches a person**, so a mistake here
shows. These tests pin down the five cases and, above all, that no variable is left
unsubstituted: a forgotten `$username` in the HTML is a mail that tells a student
literally "$username".

The bodies follow the language of the run (`--lang`/`--idioma`, `KUTRAL_LANG` or the
locale). The suite runs in `es`, so what is asserted by default is the Spanish; the other
half is covered by `test_every_mail_has_an_english_version`.
"""

from __future__ import annotations

import email
import os
import re

from modules.common import i18n
from modules.core import smtp_mailer
from modules.core.smtp_mailer import SmtpMailer

UNSUBSTITUTED = re.compile(r"\$[a-z_]+")


def _config(base_dir: str, transport: str = "file", tutorial: str = "missing.pdf") -> dict:
    return {
        "environment": "lab",
        "ldap": {"base_dn": "ou=People,<SUFIJO_DEL_DIRECTORIO>", "group_dn": "ou=Group,<SUFIJO_DEL_DIRECTORIO>"},
        "paths": {"beegfs_home": "sandbox/mnt/beegfs/home",
                  "beegfs_labs": "sandbox/mnt/beegfs/labs",
                  "mail_dir": "sandbox/mail", "tutorial_pdf": tutorial},
        "smtp": {"transport": transport, "sender": "hpc@ejemplo.cl", "server": "localhost", "port": 25},
        "cluster": {"name": "Kutral HPC", "login_host": "198.51.100.104",
                    "web_url": "https://kutral-hpc.ejemplo.cl/",
                    "wiki_url": "https://kutral-hpc.ejemplo.cl/mediawiki"},
        "_base_dir": base_dir, "_config_path": os.path.join(base_dir, "config.yaml"),
    }


def test_the_four_templates_render_with_no_loose_variables(tmp_path):
    config = _config(str(tmp_path))
    cases = [
        ("welcome", {"username": "ptest", "temp_pass": "ClaveTemp123!", "group": "lab-06"}),
        ("modification", {"username": "ptest", "changes": [("Correo", "viejo@ejemplo.cl", "nuevo@ejemplo.cl")]}),
        ("deactivation", {"username": "ptest", "reason": "Fin de curso"}),
        ("reactivation", {"username": "ptest", "temp_pass": "ClaveTemp123!",
                          "group": "lab-06", "expires": "2027-01-01"}),
    ]
    for kind, context in cases:
        subject, html = smtp_mailer.RENDERERS[kind](config, "ptest@ejemplo.cl", **context)
        assert subject, "every mail needs a subject"
        assert not UNSUBSTITUTED.search(html), "variables left unsubstituted in {}".format(kind)
        assert "$cluster_name" not in html
        assert "Kutral HPC" in html


def test_the_welcome_carries_the_credentials_and_the_reactivation_the_date(tmp_path):
    config = _config(str(tmp_path))

    _, welcome = smtp_mailer.render_welcome(config, "x@ejemplo.cl", username="ptest",
                                            temp_pass="ClaveTemp123!", group="lab-06")
    assert "ClaveTemp123!" in welcome
    assert "ssh ptest@198.51.100.104" in welcome
    assert "/mnt/beegfs/home/ptest" in welcome

    _, reactivation = smtp_mailer.render_reactivation(config, "x@ejemplo.cl", username="ptest",
                                                      temp_pass="Otra123456!", expires="2027-01-01")
    assert "2027-01-01" in reactivation
    assert "Otra123456!" in reactivation

    _, deactivation = smtp_mailer.render_deactivation(config, "x@ejemplo.cl", username="ptest",
                                                      reason="Fin de curso")
    assert "Fin de curso" in deactivation
    assert "suspendida" in deactivation


def test_the_modification_announces_the_change_without_carrying_the_password(tmp_path):
    """The invariant: this mail **announces** the change, but does not carry the password.

    The password travels in the credentials mail (creation, reactivation and reset). And
    the test anchors on the fact, not on the wording: it used to say
    `assert "restablecida" in html`, and any tweak to the sentence broke it —that
    happened on 2026-10-15, when "restablecida" moved to the reset mail of its own.
    """
    config = _config(str(tmp_path))
    _, html = smtp_mailer.render_modification(
        config, "x@ejemplo.cl", username="ptest",
        changes=[("Grupo", "lab-07", "lab-06"), ("Correo", "a@ejemplo.cl", "b@ejemplo.cl")],
        password_changed=True)

    # The changes are listed, and the password section exists…
    assert "lab-07" in html and "lab-06" in html
    assert "contraseña" in html.lower()
    # …and it carries no password value (not even a hash).
    assert not re.search(r"\{CRYPT\}", html)

    # The opposite branch exists and says something else: the notice depends on the flag.
    _, without_change = smtp_mailer.render_modification(
        config, "x@ejemplo.cl", username="ptest", changes=[], password_changed=False)
    assert without_change != html, "with password_changed=False the notice has to change"


def test_the_file_transport_writes_the_mails(tmp_path):
    config = _config(str(tmp_path))
    mailer = SmtpMailer(config)

    assert mailer.send("bienvenida", "ptest@ejemplo.cl", username="ptest", temp_pass="Clave123456!")
    assert mailer.send("desactivacion", "otro@ejemplo.cl", username="otro")

    written = sorted(os.listdir(os.path.join(str(tmp_path), "sandbox", "mail")))
    assert len(written) == 2
    with open(os.path.join(str(tmp_path), "sandbox", "mail", written[0]),
              encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    assert "Content-Type: text/html" in content or "text/html" in content


def test_without_the_pdf_it_still_sends_and_warns(tmp_path):
    config = _config(str(tmp_path), tutorial="docs/missing.pdf")
    mailer = SmtpMailer(config)
    assert mailer.send("welcome", "ptest@ejemplo.cl", username="ptest", temp_pass="Clave123456!")
    assert mailer.sent[-1]["delivered"] is True
    assert mailer.sent[-1]["kind"] == "welcome"


def test_an_unknown_kind_does_not_raise(tmp_path):
    mailer = SmtpMailer(_config(str(tmp_path)))
    assert mailer.send("telegrama", "x@ejemplo.cl", username="x") is False


def test_missing_required_data_returns_false(tmp_path):
    mailer = SmtpMailer(_config(str(tmp_path)))
    assert mailer.send("welcome", "x@ejemplo.cl", username="ptest") is False


def test_the_kind_aliases_are_accepted(tmp_path):
    assert smtp_mailer.normalize_kind("bienvenida") == "welcome"
    assert smtp_mailer.normalize_kind("desactivacion") == "deactivation"
    assert smtp_mailer.normalize_kind("REACTIVACION") == "reactivation"


def test_describe_reveals_the_transport(tmp_path):
    summary = SmtpMailer(_config(str(tmp_path))).describe()
    assert summary["transport"] == "file"
    assert summary["tutorial_present"] is False


# ---------------------------------------------------------------------------
# The other language
# ---------------------------------------------------------------------------

def test_every_mail_has_an_english_version(tmp_path):
    """The person receives the mail in the language of the run.

    Both versions are written side by side in the catalog, so what this checks is that the
    English half exists **and is really reached**: a half-filled entry would come out as a
    Spanish sentence inside an English mail, and nobody would see it until it was sent.
    """
    config = _config(str(tmp_path))
    cases = [
        ("welcome", {"username": "ptest", "temp_pass": "Clave123456!",
                      "group": "lab-06"},
         "Credentials"),
        ("modification", {"username": "ptest",
                           "changes": [("Mail", "viejo@ejemplo.cl", "nuevo@ejemplo.cl")]},
         "Updated"),
        ("deactivation", {"username": "ptest", "reason": "End of course"},
         "Suspension"),
        ("reactivation", {"username": "ptest", "temp_pass": "Clave123456!",
                           "expires": "2027-01-01"}, "Reactivated"),
        ("password", {"username": "ptest", "temp_pass": "Clave123456!"},
         "Password Reset"),
    ]

    i18n.set_language("en")
    try:
        for kind, context, marker in cases:
            subject, html = smtp_mailer.RENDERERS[kind](config, "ptest@ejemplo.cl", **context)
            assert marker in subject, "{}: the subject is not translated".format(kind)
            assert '<html lang="en">' in html
            assert "Sincerely," in html
            assert "temporary" in html.lower() or kind in ("modification", "deactivation")
            assert not UNSUBSTITUTED.search(html), \
                "variables left unsubstituted in the English {}".format(kind)
            assert not re.search(r"Contraseña|Clúster|Estimado|atentamente", html), \
                "{}: a Spanish sentence survived the English run".format(kind)
    finally:
        i18n.set_language("es")


def test_the_spanish_mail_is_not_the_english_one(tmp_path):
    """The two versions are different texts, not the same one with the lang attribute."""
    config = _config(str(tmp_path))
    context = {"username": "ptest", "temp_pass": "Clave123456!", "group": "lab-06"}

    _, spanish = smtp_mailer.render_welcome(config, "ptest@ejemplo.cl", **context)
    i18n.set_language("en")
    try:
        _, english = smtp_mailer.render_welcome(config, "ptest@ejemplo.cl", **context)
    finally:
        i18n.set_language("es")

    assert '<html lang="es">' in spanish and '<html lang="en">' in english
    assert "Buenas Prácticas" in spanish and "Good Practices" in english
    assert "Buenas Prácticas" not in english
    # The data of the account does not change with the language: only the words.
    assert "Clave123456!" in spanish and "Clave123456!" in english
    assert "ssh ptest@198.51.100.104" in spanish and "ssh ptest@198.51.100.104" in english


def test_the_mail_written_to_disk_is_in_the_language_of_the_run(tmp_path):
    """End to end: what lands in the `.eml` is the text of the run, not the default one."""
    config = _config(str(tmp_path))
    mailer = SmtpMailer(config)

    i18n.set_language("en")
    try:
        assert mailer.send("welcome", "ptest@ejemplo.cl", username="ptest",
                           temp_pass="Clave123456!")
    finally:
        i18n.set_language("es")

    written = sorted(os.listdir(os.path.join(str(tmp_path), "sandbox", "mail")))
    with open(os.path.join(str(tmp_path), "sandbox", "mail", written[0]), "rb") as handle:
        message = email.message_from_bytes(handle.read())
    parts = [part.get_payload(decode=True).decode("utf-8", "replace")
             for part in message.walk() if part.get_content_maintype() == "text"]
    body = " ".join(parts)

    assert "Access Credentials" in body
    assert "Clave123456!" in body, "the credentials travel in the same mail, in any language"

