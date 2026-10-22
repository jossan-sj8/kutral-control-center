"""Language selection and message lookup.

The language is chosen once, when the program starts, from the first of these that
gives an answer:

1. the `--lang` / `--idioma` flag on the command line
2. the `KUTRAL_LANG` environment variable
3. the session locale (`LC_ALL`, `LC_MESSAGES`, then `LANG`)
4. Spanish: the cluster's operators are Spanish speakers, so that is the fallback
   when the session says nothing useful (`LANG=C`, for instance)

Everything the operator reads comes from `messages.MESSAGES`, which carries both
languages side by side. The mails sent to people come from that same catalog (the `mail.*`
keys), so they go out in the language of the run too — see `core/smtp_mailer.py`.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

from .messages import MESSAGES

#: The languages the catalog carries.
LANGUAGES = ("es", "en")

#: Used when neither the flag, nor the variable, nor the locale say anything.
DEFAULT_LANGUAGE = "es"

#: Environment variable that overrides the locale (and is overridden by the flag).
ENVIRONMENT_VARIABLE = "KUTRAL_LANG"

#: The flags that choose the language, in both spellings.
LANGUAGE_FLAGS = ("--lang", "--idioma")

_language: str = DEFAULT_LANGUAGE


def normalize(code: Optional[str]) -> Optional[str]:
    """Map a language code or a locale name to `es`/`en`, or None if unknown.

    Accepts what an operator would actually type or have in the environment:
    `en`, `EN`, `en_US.UTF-8`, `es_CL`, `spanish`… Anything else is None, so an
    unknown value never leaves the tool mute: it keeps the language it had.
    """
    if not code:
        return None
    code = str(code).strip().lower().replace("_", "-")
    if code.startswith("en") or code.startswith("english"):
        return "en"
    if code.startswith("es") or code.startswith("spanish"):
        return "es"
    return None


def from_argv(argv: Sequence[str]) -> Optional[str]:
    """Read the language flag from the raw arguments, before the parser exists.

    The parser's own help texts have to be written in one language, so the language
    must be known *before* `build_parser()` runs: hence this small pre-scan. It
    accepts the flag anywhere, with a space or with `=`.
    """
    for position, item in enumerate(argv):
        for flag in LANGUAGE_FLAGS:
            value = None
            if item == flag and position + 1 < len(argv):
                value = argv[position + 1]
            elif item.startswith(flag + "="):
                value = item.split("=", 1)[1]
            found = normalize(value)
            if found:
                return found
    return None


def detect(explicit: Optional[str] = None,
           environ: Optional[Dict[str, str]] = None) -> str:
    """Resolve the language: the argument, then the variable, then the locale."""
    entorno = os.environ if environ is None else environ
    candidates: List[Optional[str]] = [
        explicit,
        entorno.get(ENVIRONMENT_VARIABLE),
        entorno.get("LC_ALL"),
        entorno.get("LC_MESSAGES"),
        entorno.get("LANG"),
    ]
    for candidate in candidates:
        found = normalize(candidate)
        if found:
            return found
    return DEFAULT_LANGUAGE


def set_language(code: Optional[str]) -> str:
    """Set the language and return it. An unknown value changes nothing."""
    global _language
    found = normalize(code)
    if found:
        _language = found
    return _language


def language() -> str:
    """The language in use right now."""
    return _language


def t(catalog_key: str, **values: object) -> str:
    """Look up a message and fill in its placeholders.

    The first parameter is named `catalog_key` —and **not** `key` or `message`— on
    purpose: both of those names are used *as placeholders* in the catalog (`{key}` in
    the duplicate-key error, `{message}` in the CLI prefixes), and a placeholder that
    shares its name with the parameter collides with it. With the parameter called
    `message`, `t("cli.error.prefix", message=exc)` raised
    `TypeError: t() got multiple values for argument 'message'`, which turned every
    error path of the CLI into a second, unrelated crash.

    A missing key or a missing translation is a programming error, and it is reported
    as one: an empty message in the operator's face is worse than a crash.
    """
    try:
        entry = MESSAGES[catalog_key]
    except KeyError:
        raise KeyError("message not defined: {!r}".format(catalog_key))
    text = entry.get(_language) or entry.get(DEFAULT_LANGUAGE)
    if not text:
        raise KeyError("message without text: {!r}".format(catalog_key))
    return text.format(**values) if values else text
