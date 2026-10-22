"""The reset mail carries the temporary password.

Until 2026-10-15 that mail said *"Su contraseña fue restablecida. Se le entregará por un
canal aparte"*: whoever asked for access was left waiting for a password nobody was ever
going to send. It really happened, to a student who needed to get in for their thesis.

The person who needs to get in is the one who should have to guess the least: if the
password is generated, it travels in the same mail that announces it —just like in
creation and reactivation— together with the instruction on how to change it.

Note on the assertions: the mail bodies follow the language of the run, and the suite
runs in `es`, so what is read here is the Spanish text. `test_mailer.py` covers the
English half of every template.
"""

from __future__ import annotations

from modules.core import smtp_mailer
from modules.testing.fake_services import build_environment
from modules.users import lifecycle


def _env_that_sends(config: dict):
    """Copy of the config with the mail policy set to `always`."""
    copy = dict(config)
    copy["cluster"] = dict(config["cluster"], send_mail="always")
    return build_environment(copy)


def test_the_reset_sends_the_password(config: dict):
    env = _env_that_sends(config)

    result = lifecycle.reset_password(env, "aalarcon")

    call = env.mailer.last()
    assert call is not None and call["kind"] == "password", \
        "the reset has a mail of its own, not the 'modification' one"
    assert call["context"]["temp_pass"] == result["password"]
    assert result["mail_sent"] is True

    with open(call["path"], encoding="utf-8") as handle:
        assert result["password"] in handle.read(), \
            "the password has to be written in the mail that goes out"


def test_the_mail_explains_how_to_change_it(config: dict):
    """The text comes from the real renderer, and it promises no other channel."""
    subject, body = smtp_mailer.render_password_reset(config, "a@ejemplo.cl", "aalarcon", "Ab1.Cd2")

    assert "Ab1.Cd2" in body
    assert "passwd" in body
    assert "canal aparte" not in body
    assert "Contraseña restablecida" in subject


def test_every_mail_kind_is_registered():
    """A renderer with no alias in `KIND_ALIASES` is useless: `send` rejects it.

    It happened on 2026-10-15: `reset-password` asked for the kind `password`, the
    renderer existed… and `normalize_kind` rejected it with "Tipo de correo desconocido".
    The password was changed, the mail never went out, and the person was left waiting.
    """
    for kind in smtp_mailer.RENDERERS:
        assert smtp_mailer.normalize_kind(kind) == kind


def test_the_three_templates_that_hand_over_a_password_carry_it(config: dict):
    """Creation, reactivation and reset: all three, with user, password and SSH access."""
    for render, arguments in ((smtp_mailer.render_welcome, {}),
                              (smtp_mailer.render_reactivation, {}),
                              (smtp_mailer.render_password_reset, {})):
        _, body = render(config, "a@ejemplo.cl", "aalarcon", "Ab1.Cd2")
        assert "Ab1.Cd2" in body, render.__name__
        assert "ssh aalarcon@" in body, render.__name__
