"""One command per operation. None of them prints: all of them return data.

That is why the same command serves the text output, `--json` and the tests. The
environment header and the formatting are decided by `kutral_mgr.py`.

Two rules that apply to every write command:

  - **The adapters the command needs are required** (`require_adapters`), instead of
    doing half the job and leaving the cluster in a worse state.
  - **The mail policy is resolved here**: if it is `ask` and there is a terminal, it
    asks; if not, `--enviar-correo` / `--no-enviar-correo` or the configuration rule.

Every message the operator reads comes from the bilingual catalog
(`common/messages.py`): the code says *what* it means, and the catalog knows how to
say it in Spanish and in English.
"""

from __future__ import annotations

import datetime
import sys
from typing import Any, Dict, List, Optional

from ..common import prompts
from ..common.errors import EntryNotFound, KutralError, OperationCancelled
from ..common.i18n import t
from ..core import config as cfgmod
from ..groups import creation_group, deletion_group, modification_group
from ..reports import ldap_export
from ..users import consultation, creation, deletion, lifecycle, modification
from .environment import describe_environment, require_adapters

#: What each kind of command needs so as not to stop halfway.
WRITE_SLURM = ["slurm", "identity"]
WRITE_FULL = ["slurm", "storage", "identity"]


def _result(command: str, message: str, **extra: Any) -> Dict[str, Any]:
    return dict({"command": command, "message": message}, **extra)


def _mail_flag(args: Any, environment: Any, question: str) -> Optional[bool]:
    """Decide whether mail goes out: an explicit flag, or the question when it applies.

    The global flag is `--enviar-correo` and not `--mail`, because `--mail` is the
    person's address in `create-user` and `modify-user`: two options with the same
    name in the same parser make it impossible to build.
    """
    bandera = getattr(args, "enviar_correo", None)
    if bandera is not None:
        return bool(bandera)
    if environment.dry_run:
        return False
    if environment.mail_policy == "ask" and not getattr(args, "yes", False) and sys.stdin.isatty():
        return prompts.confirm(question, default=False)
    return None      # the domain decides from the policy


def parse_expiry(value: Optional[str], environment: Any) -> Optional[datetime.date]:
    """Interpret `--expires` according to the configured policy.

    Accepts: nothing (uses `cluster.expire_default`), `nunca`/`never`, `2028-12-31`,
    `fin-de-anio`/`year-end`, and durations such as `2a`/`2y`, `18m`, `90d`. All the
    logic lives in `core/expiry.py`: here the configuration is just passed through.
    """
    from ..core import expiry as expiry_mod

    return expiry_mod.parse_expiry(value, environment.config)


def _require_user(environment: Any, username: str) -> Dict[str, Any]:
    snapshot = consultation.user_snapshot(environment, username)
    if not snapshot.get("exists"):
        raise EntryNotFound(t("msg.user.not_found", username=username))
    return snapshot


# ---------------------------------------------------------------------------
# Reading (these also work against the real cluster)
# ---------------------------------------------------------------------------

def status(environment: Any, args: Any) -> Dict[str, Any]:
    summary_data = consultation.summary(environment)
    summary_data["environment"] = describe_environment(environment)
    summary_data["config"] = {
        "ldap": environment.config["ldap"]["server"],
        "beegfs_home": cfgmod.path_for(environment.config, "beegfs_home"),
        "beegfs_labs": cfgmod.path_for(environment.config, "beegfs_labs"),
        "mail": cfgmod.get(environment.config, "smtp.transport"),
        "send_mail": environment.mail_policy,
    }
    return _result("status", t("msg.status.summary", users=summary_data["users"],
                               groups=summary_data["groups"]), **summary_data)


def consult(environment: Any, args: Any) -> Dict[str, Any]:
    term = (getattr(args, "term", "") or "").strip()
    if not term:
        return status(environment, args)
    matches = consultation.find_users(environment, term)
    if not matches:
        return _result("consult", t("msg.consult.none", term=term),
                       found=0, snapshots=[])
    snapshots = [consultation.user_snapshot(environment, str(entry.get("uid")))
                 for entry in matches]
    return _result("consult", t("msg.consult.found", count=len(snapshots)),
                   found=len(snapshots), snapshots=snapshots,
                   rendered=[consultation.render_snapshot(s) for s in snapshots],
                   warnings=[consultation.warnings_for(s) for s in snapshots])


def export(environment: Any, args: Any) -> Dict[str, Any]:
    path = ldap_export.export_report(environment, getattr(args, "output", None))
    rows = ldap_export.collect_rows(environment)
    return _result("export", t("msg.export.written", path=path), path=path,
                   sheets={sheet: len(items) for sheet, items in rows.items()})


def verify(environment: Any, args: Any) -> Dict[str, Any]:
    """Diagnostics: what the tool is working with, and whether the directory answers.

    The adapter list is the point of the command —it says whether each port is real or
    a double, and whether `sacctmgr` is missing on this host— so it goes into the text
    output, not only into `--json`.
    """
    info = describe_environment(environment)
    details: Dict[str, Any] = {}
    if hasattr(environment.directory, "verify"):
        details = environment.directory.verify()
    lines = [t("msg.verify.adapters")]
    for name in sorted(info["adapters"]):
        lines.append("  {:<8}: {}".format(name, info["adapters"][name]))
    if details:
        lines.append(t("msg.verify.directory"))
        for key in sorted(details):
            lines.append("  {:<8}: {}".format(key, details[key]))
    return _result("verify", t("msg.verify.summary", environment=info["environment"],
                               ldap=info["ldap"]),
                   environment=info, directory=details, rendered=["\n".join(lines)])


def gen_password(environment: Any, args: Any) -> Dict[str, Any]:
    from ..common.security import generate_secure_password

    length = int(getattr(args, "length", 0) or
                 cfgmod.get(environment.config, "cluster.password_length", 12))
    new_password = generate_secure_password(length)
    return _result("gen-password", t("msg.gen_password", length=length),
                   password=new_password)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _ask_group(environment: Any) -> str:
    """Ask for the group by name, and offer to create it when it does not exist yet.

    It used to list all 56 groups and ask for a number: a lot of noise to type one
    word. The group **must exist** —`create-user` does not create half a group—, so if
    it is missing the tool offers to create it whole (directory entry, lab folder with
    setgid, and Slurm account) in the same step, as the inherited assistant did.
    """
    while True:
        group = prompts.safe_prompt(t("prompt.group"))
        if environment.directory.group_exists(group):
            return group
        gid = environment.directory.next_gid()
        folder = (environment.storage.lab(group) if environment.storage is not None
                  else "/mnt/beegfs/labs/{}".format(group))
        print(t("msg.group.not_found", group=group))
        if not prompts.confirm(t("prompt.create_group_now", gid=gid, path=folder)):
            continue
        creation_group.create_group(environment, group, gid=gid)
        if environment.dry_run:
            print(t("msg.group.would_create_line", group=group, gid=gid))
        else:
            print(t("msg.group.created_line", group=group, gid=gid))
        return group


def _ask_signup(environment: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in interactively whatever is missing to create the account."""
    if not data.get("fullname"):
        data["fullname"] = prompts.safe_prompt(t("prompt.fullname"))
    if not data.get("username"):
        suggested = creation.suggest_username_from(data["fullname"], environment)
        data["username"] = prompts.safe_prompt(t("prompt.username"), default=suggested)
    if not data.get("group"):
        data["group"] = _ask_group(environment)
    if not data.get("mail"):
        data["mail"] = prompts.safe_prompt(t("prompt.mail"))
    for field, label in (("employee_type", t("prompt.employee_type")),
                         ("institute", t("prompt.institute")),
                         ("course", t("prompt.course"))):
        if not data.get(field):
            value = prompts.safe_prompt(label, required=False, allow_empty=True)
            if value:
                data[field] = value
    return data


def _confirm_signup(environment: Any, data: Dict[str, str], expires: Any,
                    send_mail: Optional[bool]) -> bool:
    """Show the summary of the account and ask for confirmation before creating it.

    The inherited assistant did it and the CLI had lost it. In a directory with no
    replica, seeing together what is about to be written —with the uid and gid already
    resolved— is the last net before touching the cluster.
    """
    group = data["group"]
    ids = creation.allocate_ids(environment, environment.directory.get_group(group))
    rows = [
        (t("summary.full_name"), data.get("fullname") or ""),
        (t("summary.username"), data.get("username") or ""),
        (t("summary.group"), t("summary.group_value", group=group, gid=ids["gid"])),
        (t("summary.mail"), data.get("mail") or ""),
        (t("summary.employee_type"), data.get("employee_type") or t("msg.dash")),
        (t("summary.institute"), data.get("institute") or t("msg.dash")),
        (t("summary.course"), data.get("course") or t("msg.dash")),
        (t("summary.expiry"), expires.isoformat() if expires else t("msg.no_expiry")),
        (t("summary.ids"), "{} / {}".format(ids["uid"], ids["gid"])),
        (t("summary.mail_notice"), t("summary.yes") if send_mail else t("summary.no")),
    ]
    width = max(len(label) for label, _ in rows)
    print("=" * 60)
    print("  " + t("summary.title"))
    print("=" * 60)
    for label, value in rows:
        print(" {:<{width}} : {}".format(label, value, width=width))
    print("=" * 60)
    return prompts.confirm(t("prompt.create_confirm"), default=False)


def create_user(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_FULL)
    data = {"fullname": args.full_name, "username": args.username, "group": args.group,
            "mail": args.mail, "employee_type": args.employee_type,
            "institute": args.institute, "course": args.course}
    expires = parse_expiry(args.expires, environment)
    if not args.yes:
        data = _ask_signup(environment, data)
    send_mail = _mail_flag(args, environment, t("prompt.send_welcome"))
    if not args.yes and not _confirm_signup(environment, data, expires, send_mail):
        raise OperationCancelled(
            t("msg.create.not_confirmed", username=data.get("username")))
    result = creation.create_user(environment, data, send_mail=send_mail, expires=expires)
    result["message"] = t("msg.create.done", username=result["username"],
                          group=result["group"])
    return result


def _ask_changes(environment: Any, snapshot: Dict[str, Any]) -> Dict[str, str]:
    """Ask what to modify, proposing the current value as the default."""
    labels = {"{} ({})".format(t(label), attribute): attribute
              for attribute, label in modification.EDITABLE_ATTRIBUTES.items()}
    options = sorted(labels) + [t("prompt.apply_changes")]
    changes: Dict[str, str] = {}
    while True:
        choice = prompts.choose(t("prompt.what_to_change"), options)
        if choice == t("prompt.apply_changes"):
            return changes
        attribute = labels[choice]
        current = snapshot["entry"].get(attribute)
        value = prompts.safe_prompt(t(modification.EDITABLE_ATTRIBUTES[attribute]),
                                    default=str(current) if current else None,
                                    required=False, allow_empty=True)
        if value:
            changes[attribute] = value


def modify_user(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, ["identity"])
    if args.group:
        return change_group(environment, args)
    snapshot = _require_user(environment, args.username)

    changes = {field: value for field, value in (
        ("cn", args.full_name), ("mail", args.mail), ("loginShell", args.shell),
        ("employeeType", args.employee_type), ("o", args.institute),
        ("description", args.course)) if value}
    if not changes and not args.yes:
        changes = _ask_changes(environment, snapshot)
    if not changes:
        return _result("modify-user", t("msg.modify.none"), changed=False)

    send_mail = _mail_flag(args, environment, t("prompt.send_change"))
    result = modification.modify_user(environment, args.username, changes,
                                      send_mail=send_mail)
    result["message"] = (
        t("msg.modify.done", username=args.username,
          changes=" | ".join(modification.describe_change(c)
                             for c in result.get("changes", [])))
        if result.get("changed") else t("msg.modify.same"))
    return result


def _verification_text(verified: Optional[Dict[str, Any]]) -> str:
    """Text of the verification that says **what** failed.

    It used to print `all(...)` over the whole dictionary —which included the
    membership list— and produced a bare `False`. On the cluster console that does not
    say whether the problem is the `gidNumber`, the group label or the `memberUid`,
    which is exactly what is needed to fix it.
    """
    if not verified:
        return ""
    failures = [label for field, label in (("gid_ok", "gidNumber"),
                                          ("label_ok", "departmentNumber"),
                                          ("member_ok", "memberUid"))
                if not verified.get(field)]
    if not failures:
        return t("msg.verified.yes")
    return t("msg.verified.no", fields=", ".join(failures))


def change_group(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    send_mail = _mail_flag(args, environment, t("prompt.send_group_change"))
    result = modification.change_group(environment, args.username, args.group,
                                       keep_old=bool(getattr(args, "keep_old", False)),
                                       send_mail=send_mail)
    result["message"] = t("msg.change_group", username=args.username,
                          from_group=result.get("from"), to_group=result.get("to"),
                          gid=result.get("gid"),
                          verification=_verification_text(result.get("verified")))
    return result


def add_member(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    send_mail = _mail_flag(args, environment, t("prompt.send_any"))
    result = modification.add_membership(environment, args.username, args.group,
                                         send_mail=send_mail)
    result["message"] = (t("msg.member.added", username=args.username, group=args.group)
                         if result["changed"] else
                         t("msg.member.already", username=args.username, group=args.group))
    return result


def remove_member(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    result = modification.remove_membership(environment, args.username, args.group)
    result["message"] = (t("msg.member.removed", username=args.username, group=args.group)
                         if result["changed"] else
                         t("msg.member.was_not", username=args.username, group=args.group))
    return result


def rename_user(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_FULL)
    send_mail = _mail_flag(args, environment, t("prompt.send_rename"))
    result = modification.rename_username(environment, args.username, args.new_username,
                                          move_home=not args.keep_home,
                                          send_mail=send_mail)
    result["message"] = t("msg.rename.done", username=args.username,
                          new_username=result["new_username"])
    return result


def _slurm_state(result: Dict[str, Any], dry_run: bool) -> str:
    """What happened with Slurm, without lying while simulating.

    In simulation the writes are skipped entirely, so `slurm_removed` stays False even
    though a real `deactivate` **would** remove the associations. Reporting "no
    changes" there is the opposite of what the simulation should show: that the account
    has a Slurm account which is going to be removed.
    """
    if result.get("slurm_removed"):
        return t("msg.slurm.removed")
    previous = result.get("slurm_before") or []
    if dry_run:
        return (t("msg.slurm.would_remove", accounts=", ".join(str(c) for c in previous))
                if previous else t("msg.slurm.nothing_to_remove"))
    return t("msg.slurm.unchanged")


def deactivate(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    send_mail = _mail_flag(args, environment, t("prompt.send_deactivation"))
    result = lifecycle.deactivate_user(environment, args.username, reason=args.reason,
                                       send_mail=send_mail,
                                       remove_slurm=not args.keep_slurm)
    if result.get("already_blocked"):
        result["message"] = t("msg.deactivate.already", username=args.username)
    elif environment.dry_run:
        result["message"] = t("msg.deactivate.simulated", username=args.username,
                               changes=", ".join(result["changes"]),
                               slurm=_slurm_state(result, True))
    else:
        result["message"] = t("msg.deactivate.done", username=args.username,
                               changes=", ".join(result["changes"]),
                               slurm=_slurm_state(result, False))
    return result


def reactivate(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    send_mail = _mail_flag(args, environment, t("prompt.send_new_password"))
    result = lifecycle.reactivate_user(environment, args.username,
                                       reset=not args.keep_password,
                                       expires=parse_expiry(args.expires, environment),
                                       send_mail=send_mail)
    if environment.dry_run:
        # Restoring in Slurm is skipped entirely in simulation: saying which accounts it
        # ended up in would be making it up, which is the same mistake `deactivate` had
        # when it said "Slurm: sin cambios".
        result["message"] = t("msg.reactivate.simulated", username=args.username,
                               expires=result["expires"] or t("msg.no_expiry"))
    else:
        result["message"] = t(
            "msg.reactivate.done", username=args.username,
            expires=result["expires"] or t("msg.no_expiry"),
            slurm=", ".join(result.get("slurm_accounts") or []) or t("msg.slurm.no_accounts"))
    return result


def reset_password(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, ["identity"])
    send_mail = _mail_flag(args, environment, t("prompt.send_password"))
    result = lifecycle.reset_password(environment, args.username, send_mail=send_mail)
    result["message"] = t("msg.password.reset", username=args.username)
    return result


def expire_set(environment: Any, args: Any) -> Dict[str, Any]:
    """Change the expiry of several accounts, touching nothing else.

    The usernames come as arguments or from a file (one per line), which is how long
    lists are handled: the accounts blocked at the end of term, or the seven that
    expire on 01-01.

    It does not require adapters: it writes only to the directory. What it does not
    touch —shell, Slurm, password— is exactly what should be left alone.
    """
    users: List[str] = []
    for candidate in list(getattr(args, "usernames", None) or []):
        if candidate not in users:
            users.append(str(candidate))
    path = getattr(args, "file", None)
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                name = line.strip()
                if name and not name.startswith("#") and name not in users:
                    users.append(name)
    if not users:
        raise KutralError(t("msg.expire_set.no_users"))

    expires = parse_expiry(args.expires, environment)
    changed, already, missing = [], [], []
    for username in users:
        try:
            result = lifecycle.set_expiry(environment, username, expires)
        except EntryNotFound:
            missing.append(username)
            continue
        (already if result.get("already") else changed).append(username)

    when = expires.isoformat() if expires else t("msg.no_expiry")
    message = t("msg.expire_set.done", expires=when, changed=len(changed),
                total=len(users))
    if already:
        message += t("msg.expire_set.already", count=len(already))
    if missing:
        message += t("msg.expire_set.missing", usernames=", ".join(missing))
    return _result("expire-set", message, expires=when, changed=changed,
                   already=already, missing=missing)


def delete_user(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_FULL)
    snapshot = _require_user(environment, args.username)
    if not args.yes and sys.stdin.isatty():
        prompts.press_enter(t("prompt.delete_continue", username=args.username,
                              state=snapshot["state"]))
    result = deletion.delete_user(environment, args.username,
                                  home_action=deletion.home_action_for(args),
                                  remove_slurm=not args.keep_slurm)
    warning = (result.get("identity") or {}).get("hint")
    if warning:
        result["message"] = "{}\n[!] {}".format(result["message"], warning)
    return result


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def group_create(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_FULL)
    members = [m.strip() for m in (args.members or "").split(",") if m.strip()]
    if not members and not args.yes and sys.stdin.isatty():
        text = prompts.safe_prompt(t("prompt.members"), required=False, allow_empty=True)
        members = [m.strip() for m in text.split(",") if m.strip()]
    result = creation_group.create_group(environment, args.name, gid=args.gid,
                                         members=members, is_lab=not args.no_lab)
    result["message"] = t("msg.group.created", group=result["group"],
                          gid=result["gid"], count=len(result["members"]))
    return result


def group_show(environment: Any, args: Any) -> Dict[str, Any]:
    info = creation_group.describe_group(environment, args.group)
    if not info.get("exists"):
        raise EntryNotFound(t("msg.group.not_found", group=args.group))
    info["message"] = t("msg.group.show", group=args.group, count=info["member_count"])
    info["rendered"] = [creation_group.render_group(environment, args.group)]
    return info


def group_add_member(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    send_mail = _mail_flag(args, environment, t("prompt.send_new_members"))
    result = modification_group.add_members(environment, args.group, args.usernames,
                                            send_mail=send_mail)
    result["message"] = t(
        "msg.group_add.done", group=args.group,
        added=", ".join(result["added"]) or t("msg.none"),
        missing=(t("msg.group_add.missing", usernames=", ".join(result["missing"]))
                 if result["missing"] else ""))
    return result


def group_remove_member(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_SLURM)
    result = modification_group.remove_members(environment, args.group, args.usernames,
                                               drop_slurm=bool(args.drop_slurm))
    parts = [t("msg.group_remove.removed",
               usernames=", ".join(result["removed"]) or t("msg.none"))]
    if result["not_members"]:
        parts.append(t("msg.group_remove.not_members",
                       usernames=", ".join(result["not_members"])))
    if result["skipped_primary"]:
        parts.append(t("msg.group_remove.skipped",
                       usernames=", ".join(result["skipped_primary"])))
    result["message"] = t("msg.group_remove.done", group=args.group,
                          parts=" | ".join(parts))
    return result


def group_delete(environment: Any, args: Any) -> Dict[str, Any]:
    require_adapters(environment, WRITE_FULL)
    result = deletion_group.delete_group(environment, args.group, force=bool(args.force),
                                         remove_lab_dir=bool(args.remove_lab))
    result["message"] = t("msg.group.deleted", group=args.group)
    if result.get("lab_warning"):
        result["message"] += "\n[!] " + result["lab_warning"]
    return result


#: Command name -> function. It is the only thing `kutral_mgr.py` needs to know.
HANDLERS = {
    "status": status,
    "consult": consult,
    "export": export,
    "verify": verify,
    "gen-password": gen_password,
    "create-user": create_user,
    "modify-user": modify_user,
    "change-group": change_group,
    "add-member": add_member,
    "remove-member": remove_member,
    "rename-user": rename_user,
    "deactivate": deactivate,
    "reactivate": reactivate,
    "reset-password": reset_password,
    "expire-set": expire_set,
    "delete-user": delete_user,
    "group-create": group_create,
    "group-show": group_show,
    "group-add-member": group_add_member,
    "group-remove-member": group_remove_member,
    "group-delete": group_delete,
}
