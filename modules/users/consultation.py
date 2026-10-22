"""Consult an account: gather the data and show it whole.

It was an explicit requirement —*"generate a method to consult the user's data"*— and
in the inherited flow it is spread over a hand-run `ldapsearch`, the Excel report and
reading `/etc/passwd` on two different hosts.

The query joins the **four sources** and shows them together, because the real problem
is not reading LDAP: it is that the same person looks different depending on where you
ask. A user may be active in LDAP and blocked on the host, have a Slurm account that no
longer corresponds, or a home that does not exist.

That is why `user_snapshot` includes the **local account** warning: if the user exists
in the host's `/etc/passwd`, LDAP changes will not be seen until it is cleaned, and it
is worth knowing that before promising anything to anyone.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.i18n import t
from ..core import accounts as accounts_mod
from ..core import config as cfgmod
from . import modification


def find_users(environment: Any, term: str) -> List[Dict[str, Any]]:
    """Search by exact uid, partial uid, name, mail or account type."""
    return environment.directory.search_users(term)


def state_label(environment: Any, username: str) -> str:
    """State label of the account, read from the directory."""
    entry = environment.directory.get_user(username)
    if entry is None:
        return t("msg.state.no_entry")
    return accounts_mod.state(entry)


def user_snapshot(environment: Any, username: str) -> Dict[str, Any]:
    """Gather everything known about an account, from the four sources.

    It returns a dictionary and does **not** print: that way the CLI can render it as
    text, as JSON or as a table row without querying anything again.
    """
    entry = environment.directory.get_user(username)
    if entry is None:
        return {"username": username, "exists": False}

    membresias = environment.directory.memberships(username)
    primario = modification.primary_group(environment, entry)

    cuentas_slurm: List[str] = []
    if environment.slurm is not None and environment.slurm.available:
        cuentas_slurm = environment.slurm.associations(username)

    home = str(entry.get("homeDirectory") or "")
    home_existe: Optional[bool] = None
    if environment.storage is not None and home:
        # The path is checked as it is in the directory (which is the truth in
        # production) and, if not there, the one storage resolves. In rehearsal mode
        # the config paths are relative, and without this fallback the query would
        # warn "the home does not exist" about a home that does exist — a false
        # warning is worse than no warning.
        home_existe = environment.storage.exists(home) or environment.storage.exists(
            environment.storage.home(username))

    cuenta_local = None
    if environment.identity is not None:
        cuenta_local = environment.identity.local_account_exists(username)

    return {
        "username": username,
        "exists": True,
        "dn": environment.directory.user_dn(username),
        "entry": entry,
        "state": accounts_mod.state(entry),
        "state_detail": accounts_mod.describe(entry),
        "blocked": accounts_mod.is_blocked(entry),
        "memberships": membresias,
        "primary_group": primario,
        "slurm_accounts": cuentas_slurm,
        "home": home,
        "home_exists": home_existe,
        "local_account": cuenta_local,
        "uid": entry.get("uidNumber"),
        "gid": entry.get("gidNumber"),
        "mail": entry.get("mail"),
    }


def warnings_for(snapshot: Dict[str, Any]) -> List[str]:
    """Inconsistencies worth showing, not hiding.

    Each one corresponds to a real finding on the cluster:

      - local account -> LDAP changes are not seen until it is cleaned
      - missing home -> the account exists but the person cannot work
      - not a member of its primary group -> `id` will not show the group
      - no Slurm account -> it can log in but cannot submit jobs
    """
    warnings: List[str] = []
    if not snapshot.get("exists"):
        return [t("msg.warn.no_entry")]
    if snapshot.get("local_account"):
        warnings.append(t("msg.warn.local_account"))
    if snapshot.get("home_exists") is False:
        warnings.append(t("msg.warn.no_home"))
    primary = snapshot.get("primary_group")
    if primary and primary not in (snapshot.get("memberships") or []):
        warnings.append(t("msg.warn.primary_missing", group=primary))
    if snapshot.get("slurm_accounts") == []:
        warnings.append(t("msg.warn.no_slurm"))
    return warnings


def render_snapshot(snapshot: Dict[str, Any]) -> str:
    """Text to show on screen, in the usual format."""
    if not snapshot.get("exists"):
        return t("msg.render.not_found", username=snapshot.get("username"))
    entry = snapshot["entry"]
    lines = [
        "=" * 64,
        "  {}: {}".format(t("msg.render.account"), snapshot["username"]),
        "=" * 64,
        "  {:<16}: {}".format(t("msg.render.name"),
                              entry.get("cn") or t("msg.render.no_name")),
        "  {:<16}: {}".format(t("summary.mail"),
                              snapshot.get("mail") or t("msg.render.no_mail")),
        "  {:<16}: {} / {}".format("UID / GID", snapshot.get("uid"),
                                  snapshot.get("gid")),
        "  {:<16}: {}".format(t("report.column.state"), snapshot["state"]),
        "  {:<16}: {}".format(t("msg.render.detail"), snapshot.get("state_detail")),
        "  {:<16}: {}".format(t("summary.group"),
                              snapshot.get("primary_group") or t("msg.render.unknown")),
        # The lab label is a directory attribute, not something derived from the gid:
        # there are real entries without it, and that has to be visible. The "primary
        # group" comes from the gidNumber and always returns something.
        "  {:<16}: {}".format("departmentNumber",
                              entry.get("departmentNumber") or t("msg.render.absent")),
        "  {}: {}".format(t("msg.render.member_groups"),
                          ", ".join(snapshot.get("memberships") or [])
                          or t("msg.group.render.none")),
        "  {:<16}: {}".format(t("msg.render.slurm_accounts"),
                              ", ".join(snapshot.get("slurm_accounts") or [])
                              or t("msg.render.none_slurm")),
        "  {:<16}: {} {}".format(
            "Home", snapshot.get("home") or t("msg.render.no_home"),
            "" if snapshot.get("home_exists") is None else
            (t("msg.group.render.exists") if snapshot.get("home_exists")
             else t("msg.group.render.not_exists"))),
        "  {:<16}: {}".format("Shell", entry.get("loginShell") or t("msg.render.no_shell")),
        "  {}: {} / {}".format(
            t("msg.render.type_institute"),
            entry.get("employeeType") or t("msg.render.empty"),
            entry.get("o") or t("msg.render.empty")),
        "  {:<16}: {}".format("DN", snapshot.get("dn")),
    ]
    warnings = warnings_for(snapshot)
    if warnings:
        lines.append("-" * 64)
        for warning in warnings:
            lines.append("  [!] {}".format(warning))
    return "\n".join(lines)


def summary(environment: Any) -> Dict[str, Any]:
    """Directory counts, for `status` and for the report."""
    users = environment.directory.list_users()
    by_state: Dict[str, int] = {}
    for entry in users:
        label = accounts_mod.state(entry)
        by_state[label] = by_state.get(label, 0) + 1
    groups = environment.directory.list_groups()
    result: Dict[str, Any] = {
        "users": len(users),
        "groups": len(groups),
        "by_state": by_state,
        "without_mail": len([u for u in users if not u.get("mail")]),
        # Accounts with no group label: the attribute has to be looked at, not the
        # resolved name, because `resolve_group_label` always returns something (it
        # falls back to "gid:NNNN") and the count would always be zero.
        "without_group_label": len([u for u in users if not u.get("departmentNumber")]),
        "next_uid": environment.directory.next_uid(),
        "next_gid": environment.directory.next_gid(),
    }
    if environment.slurm is not None and environment.slurm.available:
        result["slurm_available"] = True
    result["ldap"] = environment.config["ldap"]["server"]
    result["environment"] = environment.config.get("environment")
    result["mail"] = cfgmod.get(environment.config, "smtp.transport")
    return result
