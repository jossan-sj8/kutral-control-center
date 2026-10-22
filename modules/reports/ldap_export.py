"""Export the account report to Excel.

It is the `export` of the inherited flow (`reporte_cluster_ldap_*.xlsx`), which the
operator uses to review the directory with the tools already known. The same sheets and
columns are kept —`Todos`, `Activos`, `Bloqueados` in Spanish, `All`, `Active`,
`Blocked` in English— so that comparisons against the old reports keep working: running
in Spanish produces the historical names, byte for byte.

Written with `openpyxl` directly and **without pandas**: the report is three sheets of
flat rows, and a 40 MB dependency is not justified for that.
"""

from __future__ import annotations

import datetime
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ..common.errors import KutralError
from ..common.i18n import t
from ..core import accounts as accounts_mod
from ..core import config as cfgmod
from ..core.ldap_values import group_labels, resolve_group_label

#: (canonical key, column heading). The key is what the row dictionaries carry.
COLUMNS = [
    ("username", "report.column.username"),
    ("name", "report.column.name"),
    ("userid", "report.column.uid"),
    ("groupid", "report.column.gid"),
    ("group", "report.column.group"),
    ("mail", "report.column.mail"),
    ("homeDirectory", "report.column.home"),
    ("loginShell", "report.column.shell"),
    ("employeeType", "report.column.employee_type"),
    ("course", "report.column.course"),
    ("o", "report.column.institute"),
    ("shadowExpire", "report.column.shadow_expire"),
    ("state", "report.column.state"),
]

#: (canonical key, sheet-name message). The keys are stable identifiers: the sheet
#: *titles* are the ones that change with the language.
SHEETS = [
    ("all", "report.sheet.all"),
    ("active", "report.sheet.active"),
    ("blocked", "report.sheet.blocked"),
]


def sheet_titles() -> Dict[str, str]:
    """Sheet title for each canonical key, in the language in use."""
    return {key: t(message_key) for key, message_key in SHEETS}


def row_for(entry: Dict[str, Any], labels: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
    """Turn a directory entry into a report row.

    `labels` is the gid→group-names map (see `ldap_values.group_labels`): without it, an
    account with no `departmentNumber` shows `gid:9083` instead of `lab-cuatro`.
    """
    return {
        "username": entry.get("uid"),
        "name": entry.get("cn"),
        "userid": entry.get("uidNumber"),
        "groupid": entry.get("gidNumber"),
        "group": resolve_group_label(entry, labels),
        "mail": entry.get("mail"),
        "homeDirectory": entry.get("homeDirectory"),
        "loginShell": entry.get("loginShell"),
        "employeeType": entry.get("employeeType"),
        # The course lives in `description`: that is what creation stores with `--course`.
        "course": entry.get("description"),
        "o": entry.get("o"),
        "shadowExpire": entry.get("shadowExpire"),
        "state": accounts_mod.state(entry),
        # The canonical key goes separately: filtering by the label would tie the filter
        # to the language of the run, and an "Active" sheet holding the accounts of
        # "Activo" cannot depend on that.
        "state_key": accounts_mod.state_key(entry),
    }


def collect_rows(environment: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Build the three lists that go into the three sheets."""
    labels = group_labels(environment.directory.list_groups())
    all_rows = []
    for entry in environment.directory.list_users():
        all_rows.append(row_for(entry, labels))
    all_rows.sort(key=lambda row: str(row.get("username") or ""))
    active = [row for row in all_rows
              if row["state_key"] != accounts_mod.STATE_BLOCKED]
    blocked = [row for row in all_rows
               if row["state_key"] == accounts_mod.STATE_BLOCKED]
    return {"all": all_rows, "active": active, "blocked": blocked}


def export_report(environment: Any, path: Optional[str] = None) -> str:
    """Write the report and return the path of the file."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        raise KutralError(t("report.missing_openpyxl"))

    sheets = collect_rows(environment)
    if path is None:
        base = cfgmod.path_for(environment.config, "logs_dir") or "."
        os.makedirs(base, exist_ok=True)
        # The name says what it is and when it was made: `report_Users_2026-10-14.xlsx`.
        path = os.path.join(base, "report_Users_{}.xlsx".format(
            datetime.datetime.now().strftime("%Y-%m-%d")))

    titles = sheet_titles()
    book = Workbook()
    book.remove(book.active)
    for key, _ in SHEETS:
        rows = sheets.get(key) or []
        sheet = book.create_sheet(title=titles[key][:31])
        sheet.append([t(message_key) for _, message_key in COLUMNS])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([row.get(field) for field, _ in COLUMNS])
        for index, (field, message_key) in enumerate(COLUMNS, start=1):
            title = t(message_key)
            width = (max(len(title), *(len(str(r.get(field) or "")) for r in rows))
                     if rows else len(title))
            sheet.column_dimensions[
                sheet.cell(row=1, column=index).column_letter].width = min(40, width + 2)
        sheet.freeze_panes = "A2"

    _statistics_sheet(book, sheets, titles)
    book.save(path)
    return path


def _without_label(rows: List[Dict[str, Any]]) -> int:
    """Accounts whose lab could not be resolved, neither by label nor by gid.

    The shared-gid marker is read from the catalog: hardcoding the Spanish word made
    this count smaller in an English run, and a statistic that changes with the language
    is a statistic nobody can trust.
    """
    shared_mark = t("report.stats.shared_mark")
    return sum(1 for row in rows
               if str(row.get("group") or "").startswith("gid:")
               or shared_mark in str(row.get("group") or ""))


def _statistics_sheet(book: Any, sheets: Dict[str, List[Dict[str, Any]]],
                      titles: Dict[str, str]) -> None:
    """Statistics sheet: the summary that used to be taken out of Excel by hand.

    Three blocks: the totals by state, the quality of the data (how many accounts were
    left without a lab, without mail or without a login shell) and the split by lab,
    which is what gets looked at when someone asks how many people are in their group.
    """
    from openpyxl.styles import Font

    all_rows = sheets.get("all") or []
    rows: List[Any] = [
        [t("report.stats.title"), None],
        [t("report.stats.generated"), datetime.datetime.now().strftime("%Y-%m-%d %H:%M")],
        [],
        [t("report.stats.accounts"), t("report.stats.total")],
        [t("report.stats.total"), len(all_rows)],
        [t("report.stats.active"), len(sheets.get("active") or [])],
        [t("report.stats.blocked"), len(sheets.get("blocked") or [])],
        [],
        [t("report.stats.by_expiry"), t("report.stats.accounts")],
    ]
    for state, count in Counter(str(f.get("state") or "")
                               for f in all_rows).most_common():
        if state:
            rows.append([state, count])
    rows.extend([
        [],
        [t("report.stats.quality"), t("report.stats.accounts")],
        [t("report.stats.no_lab"), _without_label(all_rows)],
        [t("report.stats.no_mail"), sum(1 for f in all_rows if not f.get("mail"))],
        [t("report.stats.no_shell"),
         sum(1 for f in all_rows
             if str(f.get("loginShell") or "").endswith("nologin"))],
        [],
        [t("report.stats.by_lab"), t("report.stats.accounts")],
    ])
    for group, count in Counter(str(f.get("group") or t("report.stats.no_group"))
                                for f in all_rows).most_common():
        rows.append([group, count])

    # And the split by course, which comes from the same attribute creation writes.
    # Accounts with no course are not listed: they add nothing to the summary.
    courses = Counter(str(f.get("course") or "").strip() for f in all_rows)
    courses.pop("", None)
    if courses:
        rows.extend([[], [t("report.stats.by_course"), t("report.stats.accounts")]])
        for course, count in courses.most_common():
            rows.append([course, count])

    sheet = book.create_sheet(title=t("report.sheet.stats"))
    for row in rows:
        sheet.append(row)

    headers = {t("report.stats.title"), t("report.stats.accounts"),
               t("report.stats.by_expiry"), t("report.stats.quality"),
               t("report.stats.by_lab"), t("report.stats.by_course")}
    for row in sheet.iter_rows():
        if row and row[0].value in headers:
            for cell in row:
                cell.font = Font(bold=True)
    sheet.column_dimensions["A"].width = 40
    sheet.column_dimensions["B"].width = 12
