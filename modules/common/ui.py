"""Console output: headers, key/value pairs and tables.

It centralises the formatting so that the wizards and the CLI commands do not each
build their own `"=" * 50`.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

WIDTH = 64


def section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * WIDTH)
    print("  " + title.upper())
    print("=" * WIDTH)


def subsection(title: str) -> None:
    print("\n-- {}".format(title))


def kv(pairs: Iterable[Tuple[str, object]], label_width: int = 22) -> None:
    """Print aligned key/value pairs."""
    for label, value in pairs:
        print("  {:<{w}} : {}".format(label, "" if value is None else value, w=label_width))


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    """Print a fixed-width table, sized after its contents."""
    columns = len(headers)
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for index in range(columns):
            cell = str(row[index]) if index < len(row) else ""
            widths[index] = max(widths[index], len(cell))
    line = "  ".join("{:<{w}}".format(str(h), w=widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * widths[i] for i in range(columns)))
    for row in rows:
        print("  ".join(
            "{:<{w}}".format(str(row[i]) if i < len(row) else "", w=widths[i])
            for i in range(columns)
        ))


def ok(message: str) -> None:
    print("[+] {}".format(message))


def warn(message: str) -> None:
    print("[!] {}".format(message))


def fail(message: str) -> None:
    print("[-] {}".format(message))


def info(message: str) -> None:
    print("[i] {}".format(message))


def step(message: str) -> None:
    print("[*] {}".format(message))


def status_label(active: bool) -> str:
    """Account state label, the same one the historical report uses.

    It reads from the bilingual catalog: in Spanish it produces exactly the label the
    old reports carry, so comparisons keep working.
    """
    from .i18n import t  # imported here so this module stays dependency-free

    return t("state.active") if active else t("state.blocked")
