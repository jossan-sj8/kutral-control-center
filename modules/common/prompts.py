"""Interactive prompts: safe, validated and cancellable.

It replaces the inherited pattern of returning the string "CANCEL": here cancelling
raises `OperationCancelled`, which the CLI catches in a single place. That removes
dozens of `if value == "CANCEL"` comparisons spread over the code.

It also keeps the robust input handling of the original code: the cluster console
delivers latin-1/cp1252 bytes when the operator pastes text with accents, so the value
is decoded with retries instead of failing.

Everything the operator reads comes from the bilingual catalog
(`common/messages.py`), so the questions are asked in the language the tool was
started in; the answers are accepted in either language (`s`, `sí`, `y`, `yes`).
"""

from __future__ import annotations

import sys
from typing import Callable, List, Optional, Sequence

from .errors import OperationCancelled
from .i18n import t

try:  # readline does not exist on Windows; on the cluster it does and improves editing
    import readline  # noqa: F401
except ImportError:  # pragma: no cover
    readline = None

#: Answers that cancel an operation, in both languages.
CANCEL_WORDS = {"q", "quit", "exit", "cancelar", "salir"}

#: Answers that mean yes, in both languages.
YES_WORDS = ("s", "si", "sí", "y", "yes")

#: Answers that mean no, in both languages.
NO_WORDS = ("n", "no")

Validator = Callable[[str], Optional[str]]
"""Receives the value and returns the error message, or None if it is valid."""


def _read_line(label: str) -> Optional[str]:
    """Read one line from stdin, tolerating latin-1/cp1252 bytes."""
    try:
        sys.stdout.write(label)
        sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
    except (KeyboardInterrupt, EOFError):
        raise OperationCancelled(t("prompt.input_interrupted"))
    except AttributeError:  # stdin without a buffer (test environments)
        try:
            return input(label)
        except (KeyboardInterrupt, EOFError):
            raise OperationCancelled(t("prompt.input_interrupted"))
    if not raw:
        raise OperationCancelled(t("prompt.input_closed"))
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="ignore").strip()


def safe_prompt(
    label: str,
    required: bool = True,
    default: Optional[str] = None,
    allow_cancel: bool = True,
    validator: Optional[Validator] = None,
    allow_empty: bool = False,
) -> str:
    """Ask for a value on the console.

    Args:
        label: text to show (a ": " is appended automatically).
        required: if True, an empty answer is refused unless there is a default.
        default: proposed value; shown in brackets and used if the operator just
            presses Enter.
        allow_cancel: if True, q/quit/exit/Ctrl+C raise OperationCancelled.
        validator: function that returns an error message or None.
        allow_empty: explicitly allows an empty string (optional fields).
    """
    suffix = " [{}]".format(default) if default is not None else ""
    while True:
        value = _read_line("{} {}: ".format(label, suffix).replace("  ", " "))
        if value is None:
            raise OperationCancelled(t("prompt.input_closed"))
        if allow_cancel and value.lower() in CANCEL_WORDS:
            raise OperationCancelled(t("prompt.cancelled"))
        if not value:
            if default is not None:
                value = default
            elif allow_empty:
                return ""
            elif not required:
                return ""
            else:
                print(t("prompt.field_required"))
                continue
        if validator is not None:
            error = validator(value)
            if error:
                print("[-] {}".format(error))
                continue
        return value


def confirm(question: str, default: bool = False, allow_cancel: bool = True) -> bool:
    """Ask yes/no. Returns the default if the operator presses Enter.

    The answer is accepted in either language: the question may be asked in English and
    the hands may type `s`.
    """
    hint = t("prompt.hint_yes" if default else "prompt.hint_no")
    while True:
        value = _read_line("{} [{}]: ".format(question, hint))
        if value is None:
            raise OperationCancelled(t("prompt.input_closed"))
        if allow_cancel and value.lower() in CANCEL_WORDS:
            raise OperationCancelled(t("prompt.cancelled"))
        if not value:
            return default
        if value.lower() in YES_WORDS:
            return True
        if value.lower() in NO_WORDS:
            return False
        print(t("prompt.answer_yes_no"))


def choose(
    label: str,
    options: Sequence[str],
    default: Optional[str] = None,
    allow_cancel: bool = True,
) -> str:
    """Show a numbered list and return the chosen option."""
    if not options:
        raise ValueError(t("prompt.choice_empty"))
    print("\n{}".format(label))
    for index, option in enumerate(options, start=1):
        marker = t("prompt.choice_default") if default is not None and option == default else ""
        print("  {}. {}{}".format(index, option, marker))
    while True:
        answer = safe_prompt(t("prompt.choose_option", count=len(options)),
                             required=False, allow_cancel=allow_cancel)
        if not answer and default is not None:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        if answer in options:
            return answer
        print(t("prompt.choice_invalid"))


def press_enter(message: str = "") -> None:
    """Pause until the operator presses Enter."""
    _read_line("{}...".format(message or t("prompt.press_enter")))


def multi_value(label: str, allow_cancel: bool = True) -> List[str]:
    """Ask for a comma-separated list and return the clean items."""
    raw = safe_prompt(label + t("prompt.list_suffix"),
                      required=False, allow_empty=True, allow_cancel=allow_cancel)
    return [item.strip() for item in raw.split(",") if item.strip()]
