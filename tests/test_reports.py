"""The report's Group column, for accounts with no `departmentNumber`.

The inherited flow creates the group and sets the gid on the user, but **does not
write** `departmentNumber`: that is 17 of the 218 accounts, almost all of them created
in the last few days (`bnunez`, `cvera`, `elara`, `fjara`…). The report
showed `gid:9083` where it should say `lab-cuatro`.

And there is a worse case than the missing value: two pairs of groups share a gid (9076
and 9077). There is no picking one: both are shown, because keeping only the first would
mean inventing that person's lab.
"""

from __future__ import annotations

from modules.common import i18n
from modules.core.ldap_values import group_labels, resolve_group_label
from modules.reports import ldap_export

GROUPS = [
    {"cn": "lab-cuatro", "gidNumber": "9083"},
    {"cn": "lab-07", "gidNumber": "9000"},
    {"cn": "lab-cinco", "gidNumber": "9077"},
    {"cn": "GPRUEBA", "gidNumber": "9077"},
    {"cn": "sin-gid"},
]


def test_the_row_carries_the_course():
    """The course lives in `description` and was missing from the report (2026-10-15).

    Creation stores it with `--course`, but the report did not show it in any sheet:
    there was no way to know who belongs to which course without querying the directory.
    """
    from modules.reports import ldap_export

    assert ("course", "report.column.course") in ldap_export.COLUMNS
    i18n.set_language("es")
    assert dict(ldap_export.COLUMNS)["course"] == "report.column.course"
    assert [column for column, _ in ldap_export.COLUMNS].count("course") == 1
    row = ldap_export.row_for({"uid": "a1", "description": "Prospeccion Geofisica"})
    assert row["course"] == "Prospeccion Geofisica"
    # And with no course the cell stays empty: no value is invented.
    assert ldap_export.row_for({"uid": "a2"})["course"] is None


def test_sheet_names_are_translated():
    """The sheets are the same as the historical report, in the language of the run.

    In Spanish they stay identical to the old reports, which is what makes them
    comparable; in English they come out translated. The sheet name is text, not an
    identifier: the internal keys (`all`, `active`, `blocked`) do not change with the
    language.
    """
    from modules.reports import ldap_export

    i18n.set_language("es")
    assert ldap_export.sheet_titles() == {"all": "Todos", "active": "Activos",
                                         "blocked": "Bloqueados"}
    assert i18n.t("report.sheet.stats") == "Estadísticas"
    i18n.set_language("en")
    assert ldap_export.sheet_titles() == {"all": "All", "active": "Active",
                                         "blocked": "Blocked"}
    assert i18n.t("report.sheet.stats") == "Statistics"
    i18n.set_language("es")


def test_the_label_wins_over_the_gid():
    entry = {"departmentNumber": "lab-06", "gidNumber": "9000"}
    assert resolve_group_label(entry, group_labels(GROUPS)) == "lab-06"


def test_without_a_label_the_gid_is_resolved_against_the_groups():
    """`bnunez`: gid 9083, no departmentNumber -> lab-cuatro."""
    entry = {"gidNumber": "9083"}
    assert resolve_group_label(entry, group_labels(GROUPS)) == "lab-cuatro"


def test_a_shared_gid_shows_both_groups():
    entry = {"gidNumber": "9077"}
    label = resolve_group_label(entry, group_labels(GROUPS))
    assert "lab-cinco" in label and "GPRUEBA" in label
    # The word comes from the message catalog: the suite always runs in `es`.
    assert "compartido" in label


def test_without_a_mapping_the_bare_gid_is_shown():
    """Better `gid:9000` than asserting a group that is not known."""
    assert resolve_group_label({"gidNumber": "9000"}) == "gid:9000"
    assert resolve_group_label({"gidNumber": "9999"}, group_labels(GROUPS)) == "gid:9999"
    assert resolve_group_label({}, group_labels(GROUPS)) is None


def test_the_mapping_ignores_groups_without_a_gid():
    mapping = group_labels(GROUPS)
    assert mapping["9083"] == ["lab-cuatro"]
    assert mapping["9077"] == ["lab-cinco", "GPRUEBA"]
    assert "sin-gid" not in str(mapping)


def test_the_no_lab_statistic_counts_the_same_in_both_languages():
    """The "no lab" row used to look for the Spanish word, so in English it under-counted.

    The label is built from the catalog (`msg.group.shared_gid`), so the check has to be
    read from the catalog too. Here the label and the count are built in the same
    language, which is what a real run does.
    """
    for language in ("es", "en"):
        i18n.set_language(language)
        try:
            shared = resolve_group_label({"gidNumber": "9077"}, group_labels(GROUPS))
            assert "gid:" not in shared, "the shared gid is resolved, not bare"
            assert ldap_export._without_label(
                [{"group": shared}, {"group": "gid:9999"}]) == 2
            assert ldap_export._without_label([{"group": "lab-uno"}]) == 0
        finally:
            i18n.set_language("es")
