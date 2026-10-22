"""Mail of the control center: five templates and three transports.

It replaces the mail that is assembled by hand inside `add_users.sh` today (MIME built
with `echo`, the PDF embedded with `base64` and `msmtp "$mail"` at the end). Advantages
of doing it here:

  - The templates use `string.Template` with `$variables`, so CSS with braces does not
    have to be escaped and a variable cannot be confused with a style.
  - Sending returns True/False and **never raises an exception**: a mail that does not
    go out cannot leave a deactivation half done.
  - There is a `file` transport, which writes the mails as `.eml` files. It is the one
    offline rehearsal uses: the mails are opened and really reviewed.

Five mails, which are the changes the cluster considers important:

    welcome       creation, with credentials
    password      the password was reset: it carries the temporary one
    modification  some data of the account was changed
    deactivation  the account was suspended
    reactivation  the account came back, with a temporary password and an expiry

The four that deliver or change access (welcome, password, modification and
reactivation) carry the tutorial attached: whoever receives credentials needs the
guide at hand. See `CORREOS_CON_TUTORIAL`.

No sentence is written here: the wording lives in `common/messages.py`, under the
`mail.*` keys. That is what makes each mail go out in the language of the run
(`--lang`/`--idioma`, `KUTRAL_LANG` or the locale) without translating it twice.
"""

from __future__ import annotations

import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from string import Template
from typing import Any, Dict, List, Optional, Tuple

from ..common.i18n import language, t
from . import config as cfgmod

#: Names accepted by `send`. Spanish aliases are accepted so that the CLI and the
#: modules can write either one without surprises.
KIND_ALIASES = {
    "welcome": "welcome", "bienvenida": "welcome", "alta": "welcome",
    "create": "welcome", "creation": "welcome", "creacion": "welcome",
    "modification": "modification", "modificacion": "modification", "modify": "modification",
    "deactivation": "deactivation", "desactivacion": "deactivation", "deactivate": "deactivation",
    "reactivation": "reactivation", "reactivacion": "reactivation", "reactivate": "reactivation",
    "password": "password", "contrasena": "password", "contraseña": "password",
    "reseteo": "password", "reset": "password", "password-reset": "password",
}

LAYOUT = """<!DOCTYPE html>
<html lang="$lang">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
           color: #2c3e50; line-height: 1.6; background-color: #ffffff; margin: 0; padding: 0; }
    .email-container { max-width: 650px; margin: 0 auto; padding: 20px; }
    h3 { color: $accent; font-size: 13px; border-bottom: 1px solid #dcdde1; padding-bottom: 4px;
         margin-top: 25px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
    p { margin-bottom: 12px; font-size: 14px; }
    ul { padding-left: 20px; margin-top: 0; margin-bottom: 15px; }
    li { margin-bottom: 6px; font-size: 14px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 15px; }
    td { font-size: 14px; padding: 4px 8px 4px 0; vertical-align: top; }
    td.k { color: #7f8c8d; white-space: nowrap; }
    .code { background: #f8f9fa; border: 1px solid #e9ecef; padding: 2px 6px; border-radius: 4px;
            font-family: Consolas, Monaco, monospace; font-size: 13px; color: $accent; }
    .info-box { background: #fdfefe; border-left: 4px solid #7f8c8d; padding: 12px 15px;
                margin: 15px 0; font-size: 14px; color: #34495e; border-radius: 0 4px 4px 0; }
    .footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #e9ecef;
              font-size: 13px; color: #7f8c8d; }
    a { color: #2c3e50; text-decoration: underline; }
  </style>
</head>
<body>
  <div class="email-container">
$body
    <div class="footer">
      $signature<br>
      <b>$team</b><br>
      Universidad de O'Higgins
    </div>
  </div>
</body>
</html>"""

#: Colour of the section headings and the code boxes, per mail kind. Dark blue is the
#: tone of all the text: the only accent ever used (a green in the reactivation) was
#: removed at the operator's request, who found it out of place in an administrative
#: notice.
#: Mails that carry the tutorial attached. Whoever receives credentials —or has their
#: account changed— needs the guide at hand: not everybody goes back to look for the
#: welcome mail months later. The suspension one does not carry it: there is nothing to
#: learn to do there.
CORREOS_CON_TUTORIAL = ("welcome", "modification", "reactivation", "password")

TEXTO = "#2c3e50"

ACCENTS = {
    "welcome": TEXTO,
    "modification": TEXTO,
    "deactivation": "#7f8c8d",
    "reactivation": TEXTO,
    "password": TEXTO,
}


def normalize_kind(kind: str) -> str:
    """Translate the mail name into one of the canonical kinds.

    Any kind present in `RENDERERS` has to be here: otherwise the renderer exists but
    `send` rejects it with "Unknown mail kind" and the mail never goes out —that happened
    to `password` on 2026-10-15, with the password already changed and never reaching
    anybody—. `test_todos_los_tipos_de_correo_estan_registrados` covers it.
    """
    key = str(kind or "").strip().lower()
    if key not in KIND_ALIASES:
        raise ValueError(t("msg.mail.unknown_kind", kind=kind))
    return KIND_ALIASES[key]


# ---------------------------------------------------------------------------
# Building helpers
# ---------------------------------------------------------------------------

def _esc(value: Any) -> str:
    """Escape the minimum so a directory value does not break the HTML."""
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _p(text: str) -> str:
    return "    <p>{}</p>".format(text)


def _acceso_remoto(config: Dict[str, Any]) -> str:
    """How to get in from outside the campus.

    It goes in the **three** mails that explain how to get in (creation, reactivation and
    reset), because it is the same information: whoever comes back after months needs to
    read the same as whoever is entering for the first time. And the cluster no longer
    manages it: with an institutional mail, access is requested at DTI's Service Desk.
    """
    return _section(t("mail.section.remote_access"),
                    _p(t("mail.remote_access.vpn")) + _p(t("mail.remote_access.external")))


def _greeting(username: str) -> str:
    return _p(t("mail.greeting", username=_esc(username)))


def _section(title: str, body: str) -> str:
    return "    <h3>{}</h3>\n{}".format(_esc(title), body)


def _table(pairs: List[Tuple[str, Any]]) -> str:
    rows = ["    <table>"]
    for label, value in pairs:
        rows.append('      <tr><td class="k">{}</td><td><span class="code">{}</span></td></tr>'.format(
            _esc(label), _esc(value)))
    rows.append("    </table>")
    return "\n".join(rows)


def _info(text: str) -> str:
    return '    <div class="info-box">{}</div>'.format(text)


def _bullets(items: List[str]) -> str:
    return "    <ul>\n{}\n    </ul>".format(
        "\n".join("      <li>{}</li>".format(item) for item in items))


def _cluster(config: Dict[str, Any]) -> Dict[str, Any]:
    return config.get("cluster", {}) or {}


def _links(config: Dict[str, Any]) -> str:
    cluster = _cluster(config)
    return _bullets([
        '<b>{}:</b> <a href="{}">{}</a>'.format(
            t("mail.link.web"), cluster.get("web_url", ""), cluster.get("web_url", "")),
        '<b>{}:</b> <a href="{}">{}</a>'.format(
            t("mail.link.documentation"), cluster.get("wiki_url", ""),
            cluster.get("wiki_url", "")),
    ])


def _render(config: Dict[str, Any], kind: str, body: str) -> str:
    name = _esc(_cluster(config).get("name", "Kutral HPC"))
    return Template(LAYOUT).substitute(
        body=body,
        accent=ACCENTS.get(kind, "#2c3e50"),
        lang=language(),
        signature=t("mail.footer.signature"),
        team=t("mail.footer.team", cluster=name),
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def render_welcome(config: Dict[str, Any], to: str, username: str, temp_pass: str,
                   group: Optional[str] = None, full_name: Optional[str] = None) -> Tuple[str, str]:
    """Account creation: credentials, paths, links and the tutorial attached."""
    cluster = _cluster(config)
    body = "\n".join([
        _greeting(username),
        _p(t("mail.welcome.intro", cluster=_esc(cluster.get("name", "")))),
        _section(t("mail.section.credentials"), _table([
            (t("mail.field.username"), username),
            (t("mail.field.password"), temp_pass),
            (t("mail.field.ssh"),
             "ssh {}@{}".format(username, cluster.get("login_host", ""))),
        ])),
        _info(t("mail.temp_password.notice")),
        _section(t("mail.section.paths"), _table([
            (t("mail.field.home"),
             "{}/{}".format(cfgmod.get(config, "paths.beegfs_home"), username)),
            (t("mail.field.lab_folder"),
             "{}/{}".format(cfgmod.get(config, "paths.beegfs_labs"),
                            group or t("mail.value.no_group"))),
        ])),
        _section(t("mail.section.links"), _links(config)),
        _acceso_remoto(config),
        _section(t("mail.welcome.section.practices"), _bullets([
            t("mail.welcome.practice.credentials"),
            t("mail.welcome.practice.load"),
            t("mail.welcome.practice.editors"),
            t("mail.welcome.practice.tutorial"),
        ])),
    ])
    return t("mail.welcome.subject", cluster=_cluster(config).get("name", "Kutral HPC")), \
        _render(config, "welcome", body)


def render_modification(config: Dict[str, Any], to: str, username: str,
                        changes: Optional[List[Tuple[str, Any, Any]]] = None,
                        password_changed: bool = False) -> Tuple[str, str]:
    """Changes in the account: the touched attributes are listed.

    One single mail per operation with the whole list, instead of one per field.

    When what changes is **the password**, this is not the mail: there is a dedicated one
    (`password`) which carries it. If some day the password is changed along with other
    attributes, this one says so and the other mail is sent separately.
    """
    rows = []
    for label, before, after in (changes or []):
        rows.append((t("mail.modification.row.before", label=label),
                     before if before not in (None, "") else t("mail.value.empty")))
        rows.append((t("mail.modification.row.after", label=label), after))
    body = "\n".join([
        _greeting(username),
        _p(t("mail.modification.intro", cluster=_esc(_cluster(config).get("name", "")))),
        _section(t("mail.modification.section.changes"),
                 _table(rows) if rows else _p(t("mail.modification.no_changes"))),
        _section(t("mail.modification.section.password"), _p(
            t("mail.modification.password_changed") if password_changed
            else t("mail.modification.password_untouched"))),
        _section(t("mail.section.links"), _links(config)),
    ])
    return t("mail.modification.subject",
             cluster=_cluster(config).get("name", "Kutral HPC")), \
        _render(config, "modification", body)


def render_password_reset(config: Dict[str, Any], to: str, username: str,
                          temp_pass: str, group: Optional[str] = None) -> Tuple[str, str]:
    """Password reset: the temporary one goes **in the mail**.

    This mail used to say "it will be delivered through a separate channel". Whoever asked
    for access was left waiting for a password nobody was going to send —it happened on
    2026-10-14 with the reset mail—. If the password is generated, it travels in the same
    mail that announces it, just like in creation and reactivation, and how to change it
    is explained.
    """
    cluster = _cluster(config)
    body = "\n".join([
        _greeting(username),
        _p(t("mail.password.intro", cluster=_esc(cluster.get("name", "")))),
        _section(t("mail.section.credentials"), _table([
            (t("mail.field.username"), username),
            (t("mail.field.temp_password"), temp_pass),
            (t("mail.field.ssh"),
             "ssh {}@{}".format(username, cluster.get("login_host", ""))),
        ])),
        _info(t("mail.temp_password.notice.reset")),
        _acceso_remoto(config),
        _section(t("mail.section.links"), _links(config)),
    ])
    return t("mail.password.subject", cluster=cluster.get("name", "Kutral HPC")), \
        _render(config, "password", body)


def render_deactivation(config: Dict[str, Any], to: str, username: str,
                        reason: Optional[str] = None) -> Tuple[str, str]:
    """Account suspension."""
    body = "\n".join([
        _greeting(username),
        _p(t("mail.deactivation.intro", cluster=_esc(_cluster(config).get("name", "")))),
        _info(t("mail.deactivation.state")),
        _section(t("mail.deactivation.section.reason"),
                 _p(_esc(reason) if reason else t("mail.deactivation.default_reason"))),
        _section(t("mail.deactivation.section.next_steps"),
                 _p(t("mail.deactivation.next_steps"))),
        _section(t("mail.section.links"), _links(config)),
    ])
    return t("mail.deactivation.subject",
             cluster=_cluster(config).get("name", "Kutral HPC")), \
        _render(config, "deactivation", body)


def render_reactivation(config: Dict[str, Any], to: str, username: str,
                        temp_pass: Optional[str] = None, group: Optional[str] = None,
                        expires: Optional[str] = None) -> Tuple[str, str]:
    """Reactivation: temporary credentials and, when it applies, the expiry date.

    The date is not decoration: the inherited flow (`activate_user.sh`) computed the next
    01-01 and never wrote it, and there are 7 accounts with `shadowExpire=20819` that
    somebody had to set by hand. Here it is really applied.
    """
    body = "\n".join([
        _greeting(username),
        _p(t("mail.reactivation.intro", cluster=_esc(_cluster(config).get("name", "")))),
        _section(t("mail.section.credentials"), _table([
            (t("mail.field.username"), username),
            (t("mail.field.password"), temp_pass or t("mail.reactivation.password_unchanged")),
            (t("mail.field.ssh"),
             "ssh {}@{}".format(username, _cluster(config).get("login_host", ""))),
        ])),
        _info(t("mail.temp_password.notice")),
        _acceso_remoto(config),
        _section(t("mail.reactivation.section.validity"), _p(
            t("mail.reactivation.until", expires=_esc(expires)) if expires
            else t("mail.reactivation.forever"))),
        _section(t("mail.section.paths"), _table([
            (t("mail.field.home"),
             "{}/{}".format(cfgmod.get(config, "paths.beegfs_home"), username)),
            (t("mail.field.lab_folder"),
             "{}/{}".format(cfgmod.get(config, "paths.beegfs_labs"),
                            group or t("mail.value.no_group"))),
        ])),
        _section(t("mail.section.links"), _links(config)),
    ])
    return t("mail.reactivation.subject",
             cluster=_cluster(config).get("name", "Kutral HPC")), \
        _render(config, "reactivation", body)


RENDERERS = {
    "welcome": render_welcome,
    "modification": render_modification,
    "deactivation": render_deactivation,
    "reactivation": render_reactivation,
    "password": render_password_reset,
}

#: Fields the mailer expects per kind. It is documented so the caller knows what to
#: pass, and it is used in the error message when something is missing.
REQUIRED_CONTEXT = {
    "welcome": ("username", "temp_pass"),
    "modification": ("username",),
    "deactivation": ("username",),
    "reactivation": ("username",),
    "password": ("username", "temp_pass"),
}


# ---------------------------------------------------------------------------
# Implementation of the Mailer port
# ---------------------------------------------------------------------------

class SmtpMailer(object):
    """Real implementation of the `Mailer` port."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        smtp = config.get("smtp", {}) or {}
        self.transport = str(smtp.get("transport", "msmtp")).lower()
        self.sender = smtp.get("sender") or "hpc@ejemplo.cl"
        self.server = smtp.get("server") or "localhost"
        self.port = int(smtp.get("port") or 25)
        self.sent: List[Dict[str, Any]] = []

    # -- port -----------------------------------------------------------------

    def send(self, kind: str, to: str, **context: Any) -> bool:
        """Render and deliver. It returns True/False; it never raises."""
        try:
            canonical = normalize_kind(kind)
            renderer = RENDERERS[canonical]
            missing = [name for name in REQUIRED_CONTEXT[canonical] if not context.get(name)]
            if missing:
                print("[-] " + t("msg.mail.missing_context", kind=canonical,
                                missing=", ".join(missing)), file=sys.stderr)
                return False
            subject, html = renderer(self.config, to, **context)
            message = self._build_message(subject, to, html, kind=canonical)
            delivered = self._deliver(message, to)
            self.sent.append({"kind": canonical, "to": to, "delivered": delivered,
                              "subject": subject, "context": {k: v for k, v in context.items()
                                                              if k != "temp_pass"}})
            return delivered
        except Exception as exc:  # a mail cannot bring an operation down
            print("[-] " + t("msg.mail.prepare_failed", error=exc), file=sys.stderr)
            return False

    # -- building -------------------------------------------------------------

    def _build_message(self, subject: str, to: str, html: str, kind: str = "") -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["To"] = to
        message["From"] = self.sender
        message.set_content(t("mail.plain.alternative"))
        message.add_alternative(html, subtype="html")
        if kind in CORREOS_CON_TUTORIAL:
            self._attach_tutorial(message)
        return message

    def _attach_tutorial(self, message: EmailMessage) -> None:
        """Attach the welcome PDF if it is on disk. If not, it only warns."""
        path = cfgmod.path_for(self.config, "tutorial_pdf")
        if not path or not os.path.exists(path):
            print("[-] " + t("msg.mail.tutorial_missing", path=path), file=sys.stderr)
            return
        try:
            with open(path, "rb") as handle:
                message.add_attachment(handle.read(), maintype="application", subtype="pdf",
                                       filename=os.path.basename(path))
        except OSError as exc:
            print("[-] " + t("msg.mail.attach_failed", path=path, error=exc),
                  file=sys.stderr)

    # -- transports -----------------------------------------------------------

    def _deliver(self, message: EmailMessage, to: str) -> bool:
        if self.transport == "msmtp":
            return self._via_msmtp(message, to)
        if self.transport == "smtp":
            return self._via_smtp(message, to)
        if self.transport == "file":
            return self._via_file(message, to)
        print("[-] " + t("msg.mail.unknown_transport", transport=self.transport),
              file=sys.stderr)
        return False

    def _via_msmtp(self, message: EmailMessage, to: str) -> bool:
        """Deliver with the `msmtp` binary, which is what the cluster uses.

        `-t` makes msmtp read the recipients from the headers, so the address does not
        have to be passed on the command line.
        """
        try:
            process = subprocess.Popen(["msmtp", "-t"], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            _, error = process.communicate(input=message.as_string())
        except FileNotFoundError:
            print("[-] " + t("msg.mail.msmtp_missing"), file=sys.stderr)
            return False
        if process.returncode != 0:
            print("[-] " + t("msg.mail.msmtp_failed", to=to,
                            error=(error or "").strip()), file=sys.stderr)
            return False
        return True

    def _via_smtp(self, message: EmailMessage, to: str) -> bool:
        """Deliver over plain SMTP (for instance a local relay on port 25)."""
        try:
            with smtplib.SMTP(self.server, self.port, timeout=15) as client:
                client.send_message(message)
            return True
        except Exception as exc:
            print("[-] " + t("msg.mail.smtp_failed", to=to, server=self.server,
                            port=self.port, error=exc), file=sys.stderr)
            return False

    def _via_file(self, message: EmailMessage, to: str) -> bool:
        """Write the mail as `.eml`. It is the offline rehearsal transport."""
        outdir = cfgmod.path_for(self.config, "mail_dir") or "sandbox/mail"
        try:
            os.makedirs(outdir, exist_ok=True)
            index = len(self.sent) + 1
            safe_to = to.replace("@", "_at_").replace("/", "_")
            path = os.path.join(outdir, "{:03d}-{}.eml".format(index, safe_to))
            with open(path, "wb") as handle:
                handle.write(message.as_bytes())
            return True
        except OSError as exc:
            print("[-] " + t("msg.mail.file_failed", outdir=outdir, error=exc),
                  file=sys.stderr)
            return False

    # -- diagnostics ----------------------------------------------------------

    def describe(self) -> Dict[str, Any]:
        """Transport summary, for `status` and for the simulation."""
        return {
            "transport": self.transport,
            "sender": self.sender,
            "server": self.server,
            "port": self.port,
            "tutorial": cfgmod.path_for(self.config, "tutorial_pdf"),
            "tutorial_present": bool(cfgmod.path_for(self.config, "tutorial_pdf")
                                     and os.path.exists(cfgmod.path_for(self.config, "tutorial_pdf") or "")),
        }
