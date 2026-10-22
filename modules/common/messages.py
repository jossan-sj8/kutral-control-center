"""Every text the operator reads, in Spanish and English.

One entry per message, both languages side by side: translating does not depend on
remembering to edit three places. Keys are stable English identifiers; the texts can
be reworded without touching the code.

The mails sent to people are here as well: the mail a person receives follows the
language of the run, exactly like the console. `core/smtp_mailer.py` builds the HTML and
the tables; the words are in this catalog.
"""

MESSAGES = {
    # ---------------------------------------------------------------------
    # The parser
    # ---------------------------------------------------------------------
    "parser.description": {
        "es": "Kutral Control Center: ciclo de vida de usuarios y grupos del clúster Kutral.",
        "en": "Kutral Control Center: user and group lifecycle on the Kutral cluster.",
    },
    "flag.config": {
        "es": "archivo de configuración",
        "en": "configuration file",
    },
    "flag.simulate": {
        "es": "recorrer el flujo sin escribir nada",
        "en": "walk the whole flow without writing anything",
    },
    "flag.json": {
        "es": "salida en JSON",
        "en": "JSON output",
    },
    "flag.yes": {
        "es": "no preguntar nada",
        "en": "do not ask anything",
    },
    "flag.send_mail": {
        "es": "enviar correo aunque la política no lo pida",
        "en": "send mail even if the policy does not ask for it",
    },
    "flag.no_send_mail": {
        "es": "no enviar correo",
        "en": "do not send mail",
    },
    "flag.no_header": {
        "es": "no imprimir la cabecera de entorno (el aviso de simulación se imprime igual)",
        "en": "do not print the environment header (the simulation notice is printed anyway)",
    },
    "flag.lang": {
        "es": "idioma de los mensajes: es o en (también KUTRAL_LANG y el locale de la sesión)",
        "en": "language of the messages: en or es (also KUTRAL_LANG and the session locale)",
    },

    # ---------------------------------------------------------------------
    # What each command does (the help list)
    # ---------------------------------------------------------------------
    "help.cmd.status": {"es": "resumen del directorio y del entorno",
                        "en": "summary of the directory and the environment"},
    "help.cmd.consult": {"es": "consultar una cuenta por usuario, nombre o correo",
                         "en": "look up an account by username, name or mail"},
    "help.cmd.export": {"es": "exportar el reporte del directorio a Excel",
                        "en": "export the directory report to Excel"},
    "help.cmd.verify": {"es": "diagnóstico: entorno y conexión al directorio",
                        "en": "diagnostics: environment and directory connection"},
    "help.cmd.gen_password": {"es": "generar una contraseña temporal",
                              "en": "generate a temporary password"},
    "help.cmd.create_user": {"es": "crear una cuenta",
                             "en": "create an account"},
    "help.cmd.modify_user": {"es": "modificar datos de una cuenta (y su grupo con --group)",
                             "en": "modify account data (and its group with --group)"},
    "help.cmd.change_group": {"es": "mover la cuenta a otro grupo",
                              "en": "move the account to another group"},
    "help.cmd.add_member": {"es": "sumar la cuenta a un grupo secundario",
                            "en": "add the account to a secondary group"},
    "help.cmd.remove_member": {"es": "quitar la cuenta de un grupo secundario",
                               "en": "remove the account from a secondary group"},
    "help.cmd.rename_user": {"es": "cambiar el nombre de usuario",
                             "en": "change the username"},
    "help.cmd.deactivate": {"es": "suspender una cuenta",
                            "en": "suspend an account"},
    "help.cmd.reactivate": {"es": "reactivar una cuenta, con contraseña temporal",
                            "en": "reactivate an account, with a temporary password"},
    "help.cmd.reset_password": {"es": "generar una contraseña temporal nueva",
                                "en": "generate a new temporary password"},
    "help.cmd.expire_set": {"es": "cambiar el vencimiento de varias cuentas de una vez",
                            "en": "change the expiry of several accounts at once"},
    "help.cmd.delete_user": {"es": "borrar una cuenta (por defecto conserva el home)",
                             "en": "delete an account (keeps the home by default)"},
    "help.cmd.group_create": {"es": "crear un grupo con sus miembros desde el inicio",
                              "en": "create a group with its members from the start"},
    "help.cmd.group_show": {"es": "mostrar un grupo y sus miembros",
                            "en": "show a group and its members"},
    "help.cmd.group_add_member": {"es": "sumar miembros a un grupo",
                                  "en": "add members to a group"},
    "help.cmd.group_remove_member": {"es": "quitar miembros de un grupo",
                                     "en": "remove members from a group"},
    "help.cmd.group_delete": {"es": "borrar un grupo",
                              "en": "delete a group"},
    "help.arg.term": {"es": "usuario, nombre, correo o tipo de cuenta",
                      "en": "username, name, mail or account type"},

    # ---------------------------------------------------------------------
    # Per-command flags
    # ---------------------------------------------------------------------
    "flag.output": {"es": "ruta del .xlsx (por defecto, en logs/)",
                    "en": "path of the .xlsx file (defaults to logs/)"},
    "flag.length": {"es": "largo de la contraseña (por defecto, el del clúster)",
                    "en": "password length (defaults to the cluster's)"},
    "flag.full_name": {"es": "nombre completo de la persona",
                       "en": "full name of the person"},
    "flag.username": {"es": "nombre de usuario (sin acentos, en minúsculas)",
                      "en": "username (no accents, lowercase)"},
    "flag.group": {"es": "grupo primario",
                   "en": "primary group"},
    "flag.mail": {"es": "correo de la persona",
                  "en": "the person's mail address"},
    "flag.employee_type": {"es": "tipo de cuenta (student, postdoc, …)",
                           "en": "account type (student, postdoc, …)"},
    "flag.institute": {"es": "institución (atributo o)",
                       "en": "institution (attribute o)"},
    "flag.course": {"es": "curso al que pertenece (atributo description)",
                    "en": "course the person belongs to (attribute description)"},
    "flag.expires": {"es": "YYYY-MM-DD, fin-de-anio o nunca",
                     "en": "YYYY-MM-DD, year-end or never"},
    "flag.shell": {"es": "shell de login",
                   "en": "login shell"},
    "flag.keep_old": {"es": "dejar el grupo anterior como membresía secundaria",
                      "en": "keep the previous group as a secondary membership"},
    "flag.keep_home": {"es": "no mover el directorio home",
                       "en": "do not move the home directory"},
    "flag.reason": {"es": "motivo de la suspensión (queda en la auditoría)",
                    "en": "reason for the suspension (kept in the audit log)"},
    "flag.keep_slurm": {"es": "no quitar la cuenta de Slurm",
                        "en": "do not remove the Slurm account"},
    "flag.keep_password": {"es": "no generar contraseña nueva",
                           "en": "do not generate a new password"},
    "flag.expire_set.value": {
        "es": "YYYY-MM-DD, fin-de-anio, nunca, o una duración (2a, 18m, 90d)",
        "en": "YYYY-MM-DD, year-end, never, or a duration (2y, 18m, 90d)"},
    "flag.expire_set.usernames": {"es": "usuarios a los que cambiar el vencimiento",
                                  "en": "usernames whose expiry changes"},
    "flag.expire_set.file": {"es": "archivo con un usuario por línea (permite listas grandes)",
                             "en": "file with one username per line (for long lists)"},
    "flag.archive_home": {"es": "archivar el home antes de borrar la cuenta",
                          "en": "archive the home before deleting the account"},
    "flag.delete_home": {"es": "borrar el home (no se puede volver atrás)",
                         "en": "delete the home (cannot be undone)"},
    "flag.members": {"es": "usuarios separados por coma",
                     "en": "comma-separated usernames"},
    "flag.no_lab": {"es": "no crear la carpeta de laboratorio",
                    "en": "do not create the lab folder"},
    "flag.usernames": {"es": "usuarios separados por espacio",
                       "en": "space-separated usernames"},
    "flag.drop_slurm": {"es": "quitar también las cuentas de Slurm",
                        "en": "also remove the Slurm accounts"},
    "flag.force": {"es": "borrar aunque tenga miembros",
                   "en": "delete even if it has members"},
    "flag.remove_lab": {"es": "borrar también la carpeta del laboratorio",
                        "en": "also delete the lab folder"},

    # ---------------------------------------------------------------------
    # What the CLI prints by itself
    # ---------------------------------------------------------------------
    "cli.header.env": {"es": "entorno: {value}", "en": "environment: {value}"},
    "cli.header.ldap": {"es": "ldap: {value}", "en": "ldap: {value}"},
    "cli.header.mode": {"es": "modo: {value}", "en": "mode: {value}"},
    "cli.header.mail": {"es": "correo: {value}", "en": "mail: {value}"},
    "cli.mode.real": {"es": "real", "en": "live"},
    "cli.mode.simulated": {"es": "SIMULACIÓN (no se escribe nada)",
                           "en": "SIMULATION (nothing is written)"},
    "cli.mode.simulated.notice": {"es": "modo: SIMULACIÓN (no se escribe nada)",
                                  "en": "mode: SIMULATION (nothing is written)"},
    "cli.result.password": {"es": "  contraseña temporal: {value}{suffix}",
                            "en": "  temporary password: {value}{suffix}"},
    "cli.result.password.simulated": {"es": "   (simulación: no se aplicó a nadie)",
                                      "en": "   (simulation: it was not applied to anyone)"},
    "cli.result.path": {"es": "  archivo: {value}", "en": "  file: {value}"},
    "cli.result.ids": {"es": "  uid/gid: {uid} / {gid}", "en": "  uid/gid: {uid} / {gid}"},
    "cli.error.prefix": {"es": "[-] {message}", "en": "[-] {message}"},
    "cli.error.cancelled": {"es": "Operación cancelada: {message}",
                            "en": "Operation cancelled: {message}"},
    "cli.error.interrupted": {"es": "Interrumpido por el operador.",
                              "en": "Interrupted by the operator."},
    "cli.password.prompt": {"es": "Contraseña LDAP: ", "en": "LDAP password: "},

    # ---------------------------------------------------------------------
    # The interactive assistant (prompts)
    # ---------------------------------------------------------------------
    "prompt.fullname": {"es": "Nombre completo", "en": "Full name"},
    "prompt.username": {"es": "Usuario", "en": "Username"},
    "prompt.group": {"es": "Grupo del usuario", "en": "Group of the user"},
    "prompt.mail": {"es": "Correo", "en": "Mail"},
    "prompt.employee_type": {"es": "Tipo de cuenta", "en": "Account type"},
    "prompt.institute": {"es": "Institución", "en": "Institution"},
    "prompt.course": {"es": "Curso (opcional)", "en": "Course (optional)"},
    "prompt.members": {
        "es": "Miembros iniciales (separados por coma, vacío = ninguno)",
        "en": "Initial members (comma-separated, empty = none)"},
    "prompt.create_group_now": {"es": "¿Crearlo ahora? gid {gid}, carpeta {path}",
                                "en": "Create it now? gid {gid}, folder {path}"},
    "prompt.what_to_change": {"es": "¿Qué desea modificar?", "en": "What do you want to change?"},
    "prompt.apply_changes": {"es": "Aplicar los cambios", "en": "Apply the changes"},
    "prompt.send_welcome": {"es": "¿Enviar el correo de bienvenida?",
                            "en": "Send the welcome mail?"},
    "prompt.send_change": {"es": "¿Avisar del cambio por correo?",
                           "en": "Announce the change by mail?"},
    "prompt.send_group_change": {"es": "¿Avisar del cambio de grupo por correo?",
                                 "en": "Announce the group change by mail?"},
    "prompt.send_any": {"es": "¿Avisar por correo?", "en": "Announce by mail?"},
    "prompt.send_rename": {"es": "¿Avisar del cambio de usuario por correo?",
                           "en": "Announce the username change by mail?"},
    "prompt.send_deactivation": {"es": "¿Avisar de la suspensión por correo?",
                                 "en": "Announce the suspension by mail?"},
    "prompt.send_new_password": {"es": "¿Enviar la nueva contraseña por correo?",
                                 "en": "Send the new password by mail?"},
    "prompt.send_password": {"es": "¿Enviar la contraseña por correo?",
                             "en": "Send the password by mail?"},
    "prompt.send_new_members": {"es": "¿Avisar a los nuevos miembros por correo?",
                                "en": "Announce to the new members by mail?"},
    "prompt.create_confirm": {"es": "¿Crear la cuenta así?",
                              "en": "Create the account like this?"},
    "prompt.delete_continue": {
        "es": "Se va a borrar la cuenta {username!r} ({state}). Enter para continuar",
        "en": "Account {username!r} ({state}) is about to be deleted. Press Enter to continue"},
    "prompt.field_required": {"es": "[-] Este campo es obligatorio.",
                              "en": "[-] This field is required."},
    "prompt.answer_yes_no": {"es": "[-] Responda s o n.", "en": "[-] Answer y or n."},
    "prompt.hint_yes": {"es": "S/n", "en": "Y/n"},
    "prompt.hint_no": {"es": "s/N", "en": "y/N"},
    "prompt.choose_option": {"es": "Seleccione una opción [1-{count}]",
                             "en": "Choose an option [1-{count}]"},
    "prompt.choice_default": {"es": " (por defecto)", "en": " (default)"},
    "prompt.choice_invalid": {"es": "[-] Opción inválida.", "en": "[-] Invalid option."},
    "prompt.choice_empty": {"es": "No hay opciones para elegir.",
                            "en": "There are no options to choose from."},
    "prompt.press_enter": {"es": "Presione Enter para continuar",
                           "en": "Press Enter to continue"},
    "prompt.list_suffix": {"es": " (separados por coma, vacío = ninguno)",
                           "en": " (comma-separated, empty = none)"},
    "prompt.cancelled": {"es": "Operación cancelada por el operador.",
                         "en": "Operation cancelled by the operator."},
    "prompt.input_interrupted": {"es": "Entrada interrumpida por el operador.",
                                 "en": "Input interrupted by the operator."},
    "prompt.input_closed": {"es": "Entrada cerrada (EOF).", "en": "Input closed (EOF)."},

    # ---------------------------------------------------------------------
    # What each command answers
    # ---------------------------------------------------------------------
    "msg.status.summary": {"es": "Directorio: {users} cuentas y {groups} grupos.",
                           "en": "Directory: {users} accounts and {groups} groups."},
    "msg.user.not_found": {"es": "El usuario {username!r} no existe en el directorio.",
                           "en": "User {username!r} does not exist in the directory."},
    "msg.group.not_found": {"es": "El grupo {group!r} no existe en el directorio.",
                            "en": "Group {group!r} does not exist in the directory."},
    "msg.consult.none": {"es": "Ninguna cuenta coincide con {term!r}.",
                         "en": "No account matches {term!r}."},
    "msg.consult.found": {"es": "{count} cuenta(s) encontrada(s).",
                          "en": "{count} account(s) found."},
    "msg.export.written": {"es": "Reporte escrito en {path}",
                           "en": "Report written to {path}"},
    "msg.verify.adapters": {"es": "Adaptadores:", "en": "Adapters:"},
    "msg.verify.directory": {"es": "Directorio:", "en": "Directory:"},
    "msg.verify.summary": {"es": "Entorno {environment!r} contra {ldap}.",
                           "en": "Environment {environment!r} against {ldap}."},
    "msg.gen_password": {"es": "Contraseña temporal generada ({length} caracteres).",
                         "en": "Temporary password generated ({length} characters)."},
    "msg.required.user": {"es": "El usuario {username!r} no existe en el directorio.",
                          "en": "User {username!r} does not exist in the directory."},
    "msg.create.done": {"es": "Usuario {username!r} creado en el grupo {group}.",
                        "en": "User {username!r} created in group {group}."},
    "msg.create.not_confirmed": {
        "es": "no se creó {username!r}: no se confirmó el resumen.",
        "en": "{username!r} was not created: the summary was not confirmed."},
    "msg.group.created_line": {"es": "[+] Grupo {group!r} creado (gid {gid}).",
                               "en": "[+] Group {group!r} created (gid {gid})."},
    "msg.group.would_create_line": {
        "es": "[i] Simulación: se crearía el grupo {group!r} (gid {gid}).",
        "en": "[i] Simulation: group {group!r} would be created (gid {gid})."},
    "msg.group.created": {"es": "Grupo {group!r} creado (gid {gid}) con {count} miembro(s).",
                          "en": "Group {group!r} created (gid {gid}) with {count} member(s)."},
    "msg.group.deleted": {"es": "Grupo {group!r} borrado.", "en": "Group {group!r} deleted."},
    "msg.group.show": {"es": "Grupo {group!r}: {count} miembro(s).",
                       "en": "Group {group!r}: {count} member(s)."},
    "msg.modify.none": {"es": "No se indicó ningún cambio.",
                        "en": "No change was given."},
    "msg.modify.done": {"es": "Cambios aplicados a {username!r}: {changes}",
                        "en": "Changes applied to {username!r}: {changes}"},
    "msg.modify.same": {"es": "Sin cambios: los valores ya eran esos.",
                        "en": "No changes: the values were already those."},
    "msg.verified.yes": {"es": ". Verificado: sí", "en": ". Verified: yes"},
    "msg.verified.no": {"es": ". Verificado: NO (falla {fields})",
                        "en": ". Verified: NO (failed: {fields})"},
    "msg.change_group": {
        "es": "{username}: grupo {from_group} -> {to_group} (gid {gid}){verification}.",
        "en": "{username}: group {from_group} -> {to_group} (gid {gid}){verification}."},
    "msg.member.added": {"es": "{username} agregado al grupo {group}.",
                         "en": "{username} added to group {group}."},
    "msg.member.already": {"es": "{username} ya era miembro de {group}.",
                           "en": "{username} was already a member of {group}."},
    "msg.member.removed": {"es": "{username} quitado del grupo {group}.",
                           "en": "{username} removed from group {group}."},
    "msg.member.was_not": {"es": "{username} no era miembro de {group}.",
                           "en": "{username} was not a member of {group}."},
    "msg.rename.done": {
        "es": "{username} ahora es {new_username}. Se movieron DN, grupos, Slurm y home.",
        "en": "{username} is now {new_username}. DN, groups, Slurm and home were moved."},
    "msg.slurm.removed": {"es": "quitado", "en": "removed"},
    "msg.slurm.would_remove": {"es": "se quitaría: {accounts}",
                               "en": "would be removed: {accounts}"},
    "msg.slurm.nothing_to_remove": {"es": "sin asociaciones que quitar",
                                    "en": "no associations to remove"},
    "msg.slurm.unchanged": {"es": "sin cambios", "en": "unchanged"},
    "msg.deactivate.already": {
        "es": "{username} ya estaba bloqueado: no se cambió nada.",
        "en": "{username} was already blocked: nothing changed."},
    "msg.deactivate.simulated": {
        "es": "{username}: se desactivaría ({changes}). Slurm: {slurm}.",
        "en": "{username}: would be deactivated ({changes}). Slurm: {slurm}."},
    "msg.deactivate.done": {"es": "{username} desactivado ({changes}). Slurm: {slurm}.",
                            "en": "{username} deactivated ({changes}). Slurm: {slurm}."},
    "msg.reactivate.simulated": {
        "es": "{username}: se reactivaría. Vence: {expires}.",
        "en": "{username}: would be reactivated. Expires: {expires}."},
    "msg.reactivate.done": {
        "es": "{username} reactivado. Vence: {expires}. Slurm: {slurm}.",
        "en": "{username} reactivated. Expires: {expires}. Slurm: {slurm}."},
    "msg.no_expiry": {"es": "sin vencimiento", "en": "no expiry"},
    "msg.slurm.no_accounts": {"es": "sin cuentas restauradas",
                               "en": "no accounts restored"},
    "msg.password.reset": {"es": "Contraseña temporal de {username} restablecida.",
                           "en": "Temporary password for {username} reset."},
    "msg.expire_set.no_users": {
        "es": "No hay usuarios a los que cambiar el vencimiento.",
        "en": "There are no usernames whose expiry should change."},
    "msg.expire_set.done": {
        "es": "Vencimiento actualizado a {expires} en {changed} de {total} cuentas.",
        "en": "Expiry set to {expires} on {changed} of {total} accounts."},
    "msg.expire_set.already": {"es": " Ya tenían esa fecha: {count}.",
                               "en": " Already had that date: {count}."},
    "msg.expire_set.missing": {"es": " No existen: {usernames}.",
                               "en": " Do not exist: {usernames}."},
    "msg.none": {"es": "ninguno", "en": "none"},
    "msg.dash": {"es": "-", "en": "-"},
    "msg.group_add.done": {"es": "Agregados a {group}: {added}{missing}",
                           "en": "Added to {group}: {added}{missing}"},
    "msg.group_add.missing": {"es": " (no existen: {usernames})",
                              "en": " (do not exist: {usernames})"},
    "msg.group_remove.removed": {"es": "quitados: {usernames}",
                                 "en": "removed: {usernames}"},
    "msg.group_remove.not_members": {"es": "no eran miembros: {usernames}",
                                     "en": "were not members: {usernames}"},
    "msg.group_remove.skipped": {
        "es": "omitidos por ser su grupo primario: {usernames}",
        "en": "skipped because it is their primary group: {usernames}"},
    "msg.group_remove.done": {"es": "En {group}: {parts}.", "en": "In {group}: {parts}."},

    # ---------------------------------------------------------------------
    # The account summary shown before creating
    # ---------------------------------------------------------------------
    "summary.title": {"es": "RESUMEN DE LA CUENTA", "en": "ACCOUNT SUMMARY"},
    "summary.full_name": {"es": "Nombre completo", "en": "Full name"},
    "summary.username": {"es": "Usuario", "en": "Username"},
    "summary.group": {"es": "Grupo primario", "en": "Primary group"},
    "summary.group_value": {"es": "{group} (gid {gid})", "en": "{group} (gid {gid})"},
    "summary.mail": {"es": "Correo", "en": "Mail"},
    "summary.employee_type": {"es": "Tipo de cuenta", "en": "Account type"},
    "summary.institute": {"es": "Institución", "en": "Institution"},
    "summary.course": {"es": "Curso", "en": "Course"},
    "summary.expiry": {"es": "Vencimiento", "en": "Expiry"},
    "summary.ids": {"es": "uid / gid", "en": "uid / gid"},
    "summary.mail_notice": {"es": "¿Avisar por correo?", "en": "Announce by mail?"},
    "summary.yes": {"es": "sí", "en": "yes"},
    "summary.no": {"es": "no", "en": "no"},

    # ---------------------------------------------------------------------
    # The Excel report: sheets, columns and the statistics block
    # ---------------------------------------------------------------------
    "report.sheet.all": {"es": "Todos", "en": "All"},
    "report.sheet.active": {"es": "Activos", "en": "Active"},
    "report.sheet.blocked": {"es": "Bloqueados", "en": "Blocked"},
    "report.sheet.stats": {"es": "Estadísticas", "en": "Statistics"},
    "report.column.username": {"es": "Usuario", "en": "Username"},
    "report.column.name": {"es": "Nombre", "en": "Name"},
    "report.column.uid": {"es": "UID", "en": "UID"},
    "report.column.gid": {"es": "GID", "en": "GID"},
    "report.column.group": {"es": "Grupo", "en": "Group"},
    "report.column.mail": {"es": "Correo", "en": "Mail"},
    "report.column.home": {"es": "Home", "en": "Home"},
    "report.column.shell": {"es": "Shell", "en": "Shell"},
    "report.column.employee_type": {"es": "Tipo", "en": "Type"},
    "report.column.course": {"es": "Curso", "en": "Course"},
    "report.column.institute": {"es": "Institución", "en": "Institution"},
    "report.column.shadow_expire": {"es": "shadowExpire", "en": "shadowExpire"},
    "report.column.state": {"es": "Estado", "en": "State"},
    "report.stats.title": {"es": "ESTADÍSTICAS DEL DIRECTORIO",
                           "en": "DIRECTORY STATISTICS"},
    "report.stats.generated": {"es": "Generado", "en": "Generated"},
    "report.stats.accounts": {"es": "Cuentas", "en": "Accounts"},
    "report.stats.total": {"es": "Total", "en": "Total"},
    "report.stats.active": {"es": "Activas", "en": "Active"},
    "report.stats.blocked": {"es": "Bloqueadas", "en": "Blocked"},
    "report.stats.by_expiry": {"es": "Activas, por tipo de vencimiento",
                               "en": "Active, by expiry type"},
    "report.stats.quality": {"es": "Calidad del dato", "en": "Data quality"},
    "report.stats.no_lab": {"es": "Sin etiqueta de laboratorio",
                            "en": "Without a lab label"},
    "report.stats.no_mail": {"es": "Sin correo", "en": "Without mail"},
    "report.stats.no_shell": {"es": "Sin shell de login", "en": "Without a login shell"},
    "report.stats.by_lab": {"es": "Por laboratorio", "en": "By lab"},
    "report.stats.by_course": {"es": "Por curso", "en": "By course"},
    "report.stats.no_group": {"es": "(sin grupo)", "en": "(no group)"},
    #: Word the group label carries when two groups share a gid (`msg.group.shared_gid`).
    #: It is read from the catalog because the statistic has to count the same in both
    #: languages: searching for the Spanish "compartido" alone under-counted in English.
    "report.stats.shared_mark": {"es": "compartido", "en": "shared"},
    "report.missing_openpyxl": {
        "es": "Falta la dependencia 'openpyxl' para exportar el reporte.\n"
              "    pip install -r requirements.txt",
        "en": "The 'openpyxl' dependency is missing to export the report.\n"
              "    pip install -r requirements.txt"},

    # ---------------------------------------------------------------------
    # Validations (common/validation.py)
    # ---------------------------------------------------------------------
    "msg.username.label": {"es": "Nombre de usuario", "en": "Username"},
    "msg.username.invalid": {
        "es": "{label} inválido: {value!r}. Debe tener entre {min} y {max} caracteres, "
              "empezar con letra o guion bajo y contener sólo minúsculas, números, punto, "
              "guion o guion bajo (el punto no puede ir al inicio, al final ni repetido).",
        "en": "{label} is invalid: {value!r}. It must be between {min} and {max} "
              "characters long, start with a letter or an underscore and contain only "
              "lowercase letters, digits, dot, hyphen or underscore (the dot cannot be at "
              "the start, the end or repeated)."},
    "msg.username.taken": {"es": "El nombre de usuario {value!r} ya está en uso.",
                           "en": "The username {value!r} is already taken."},
    "msg.mail.invalid": {"es": "Correo inválido: {value!r} (ejemplo: usuaria@ejemplo.cl).",
                         "en": "Invalid mail: {value!r} (example: user@ejemplo.cl)."},
    "msg.username.none": {
        "es": "No se pudo derivar un nombre de usuario de {fullname!r}.",
        "en": "Could not derive a username from {fullname!r}."},
    "msg.username.no_free": {
        "es": "No se pudo encontrar un nombre de usuario libre para {fullname!r}.",
        "en": "Could not find a free username for {fullname!r}."},
    "msg.fullname.empty": {"es": "El nombre completo no puede estar vacío.",
                           "en": "The full name cannot be empty."},

    # ---------------------------------------------------------------------
    # Passwords (common/security.py)
    # ---------------------------------------------------------------------
    "msg.password.alphabet": {
        "es": "El alfabeto debe permitir minúsculas, mayúsculas, dígitos y símbolos.",
        "en": "The alphabet must allow lowercase letters, uppercase letters, digits and "
              "symbols."},
    "msg.password.scheme": {
        "es": "Solo se soporta el esquema {{CRYPT}} por ahora (se recibió {scheme!r}).",
        "en": "Only the {{CRYPT}} scheme is supported for now (received {scheme!r})."},
    "msg.password.crypt_failed": {"es": "El sistema no pudo calcular SHA-512 crypt.",
                                  "en": "The system could not compute SHA-512 crypt."},

    # ---------------------------------------------------------------------
    # Account state (core/accounts.py)
    # ---------------------------------------------------------------------
    "state.active": {"es": "Activo (LDAP)", "en": "Active (LDAP)"},
    "state.blocked": {"es": "Desactivado / Bloqueado (LDAP)",
                      "en": "Deactivated / Blocked (LDAP)"},
    "state.expiring": {"es": "Activo con expiración (LDAP)",
                       "en": "Active with an expiry date (LDAP)"},
    "state.no_expiry": {"es": "Activo sin expiración (LDAP)",
                        "en": "Active with no expiry (LDAP)"},
    "state.describe.blocked": {"es": "Bloqueado ({motives})", "en": "Blocked ({motives})"},
    "state.motive.shadow_expire": {"es": "shadowExpire=1", "en": "shadowExpire=1"},
    "state.motive.nologin": {"es": "shell de no-login", "en": "no-login shell"},
    "state.motive.unknown": {"es": "sin motivo aparente", "en": "no apparent reason"},
    "state.describe.until": {"es": "Activo hasta {date}", "en": "Active until {date}"},
    "state.describe.permanent": {"es": "Activo permanente (shadowExpire=-1)",
                                 "en": "Permanently active (shadowExpire=-1)"},
    "state.describe.no_attribute": {"es": "Activo (sin shadowExpire definido)",
                                    "en": "Active (no shadowExpire set)"},

    # ---------------------------------------------------------------------
    # Expiry (core/expiry.py)
    # ---------------------------------------------------------------------
    "msg.expiry.invalid": {
        "es": "Fecha de vencimiento inválida: {value!r}.\n"
              "Formas aceptadas: 2028-12-31 | fin-de-anio | 2a | 18m | 90d | nunca",
        "en": "Invalid expiry date: {value!r}.\n"
              "Accepted forms: 2028-12-31 | year-end | 2y | 18m | 90d | never"},
    "msg.expiry.overdue": {"es": "{date} (vencida hace {days} días)",
                           "en": "{date} (overdue by {days} days)"},
    "msg.expiry.in_days": {"es": "{date} (en {days} días)",
                           "en": "{date} (in {days} days)"},

    # ---------------------------------------------------------------------
    # Configuration (core/config.py)
    # ---------------------------------------------------------------------
    "msg.config.not_found": {"es": "No se encontró el archivo de configuración: {path}",
                             "en": "Configuration file not found: {path}"},
    "msg.config.not_a_map": {
        "es": "El archivo de configuración no es un mapa YAML válido: {path}",
        "en": "The configuration file is not a valid YAML map: {path}"},
    "msg.config.duplicate_key": {
        "es": "Clave duplicada '{key}' en {path} (línea {line}): YAML se queda con la "
              "última y descarta la anterior.",
        "en": "Duplicate key '{key}' in {path} (line {line}): YAML keeps the last one "
              "and discards the previous one."},
    "msg.config.environment_invalid": {
        "es": "environment inválido: {value!r} (use uno de {valid})",
        "en": "invalid environment: {value!r} (use one of {valid})"},
    "msg.config.section_not_map": {
        "es": "La sección '{section}' de {path} debe ser un mapa YAML con sub-claves.",
        "en": "The '{section}' section of {path} must be a YAML map with sub-keys."},
    "msg.config.guard_networks": {
        "es": "guard_networks debe ser una lista de redes (ej. [\"192.0.2.0/24\"]).",
        "en": "guard_networks must be a list of networks (e.g. [\"192.0.2.0/24\"])."},
    "msg.config.missing_key": {"es": "Falta ldap.{key} en {path}",
                               "en": "Missing ldap.{key} in {path}"},
    "msg.config.send_mail": {
        "es": "cluster.send_mail debe ser ask, always o never (se recibió {value!r})",
        "en": "cluster.send_mail must be ask, always or never (received {value!r})"},
    "msg.config.transport": {
        "es": "smtp.transport debe ser msmtp, smtp o file",
        "en": "smtp.transport must be msmtp, smtp or file"},
    "msg.config.blocked_by_guard": {
        "es": "Bloqueado: environment={environment!r} con ldap.server={host} cae dentro "
              "de {network}. Un entorno de pruebas no debe escribir en el clúster real.",
        "en": "Blocked: environment={environment!r} with ldap.server={host} falls inside "
              "{network}. A test environment must not write to the real cluster."},
    "msg.config.password_unavailable": {
        "es": "No hay contraseña LDAP disponible y este comando pidió no preguntarla "
              "(--yes).\nExporte {env} en la sesión, o ejecute sin --yes para "
              "escribirla en el prompt.",
        "en": "There is no LDAP password available and this command asked not to be "
              "prompted (--yes).\nExport {env} in the session, or run without --yes to "
              "type it at the prompt."},

    # ---------------------------------------------------------------------
    # Runtime environment (cli/environment.py)
    # ---------------------------------------------------------------------
    "adapter.slurm": {"es": "Slurm (asociar y desasociar cuentas)",
                      "en": "Slurm (associating and unassociating accounts)"},
    "adapter.storage": {"es": "BeeGFS (crear y mover directorios)",
                        "en": "BeeGFS (creating and moving directories)"},
    "adapter.identity": {"es": "identidad (refrescar la caché de SSSD)",
                         "en": "identity (refreshing the SSSD cache)"},
    "adapter.mailer": {"es": "correo (avisar a la persona)",
                       "en": "mail (notifying the person)"},
    "adapter.hooks": {"es": "hooks (pasos externos, como el storage de Nextcloud)",
                      "en": "hooks (external steps, such as the Nextcloud storage)"},
    "adapter.state.absent": {"es": "ausente", "en": "absent"},
    "adapter.state.double": {"es": "doble", "en": "double"},
    "adapter.state.real": {"es": "real", "en": "real"},
    "adapter.state.real_no_sacctmgr": {
        "es": "real, pero sin sacctmgr en este host",
        "en": "real, but without sacctmgr on this host"},
    "msg.env.missing_adapters": {
        "es": "Este comando necesita adaptadores que no están armados en este "
              "entorno:\n{detail}\n\nRevise cómo se construyó el entorno (--config).",
        "en": "This command needs adapters that are not wired up in this "
              "environment:\n{detail}\n\nCheck how the environment was built (--config)."},
    # ---------------------------------------------------------------------
    # Consulting an account (users/consultation.py)
    # ---------------------------------------------------------------------
    "msg.render.not_found": {
        "es": "No se encontró la cuenta {username!r} en el directorio.",
        "en": "Account {username!r} was not found in the directory."},
    "msg.state.no_entry": {"es": "No existe en el directorio",
                           "en": "Does not exist in the directory"},
    "msg.render.account": {"es": "CUENTA", "en": "ACCOUNT"},
    "msg.render.name": {"es": "Nombre", "en": "Name"},
    "msg.render.detail": {"es": "Detalle", "en": "Detail"},
    "msg.render.member_groups": {"es": "Grupos (memberUid)",
                                 "en": "Groups (memberUid)"},
    "msg.render.slurm_accounts": {"es": "Cuentas Slurm", "en": "Slurm accounts"},
    "msg.render.type_institute": {"es": "Tipo / Institución",
                                  "en": "Type / Institution"},
    "msg.render.no_name": {"es": "(sin nombre)", "en": "(no name)"},
    "msg.render.no_mail": {"es": "(sin correo)", "en": "(no mail)"},
    "msg.render.no_home": {"es": "(sin home)", "en": "(no home)"},
    "msg.render.no_shell": {"es": "(sin shell)", "en": "(no shell)"},
    "msg.render.none_slurm": {"es": "(ninguna)", "en": "(none)"},
    "msg.render.unknown": {"es": "(desconocido)", "en": "(unknown)"},
    "msg.render.absent": {"es": "(ausente)", "en": "(absent)"},
    "msg.render.empty": {"es": "(vacío)", "en": "(empty)"},
    "msg.warn.no_entry": {"es": "La cuenta no existe en el directorio.",
                          "en": "The account does not exist in the directory."},
    "msg.warn.local_account": {
        "es": "Tiene cuenta LOCAL en este host: los cambios en LDAP no se verán aquí "
              "hasta limpiarla (nsswitch resuelve 'files' antes que 'sss').",
        "en": "It has a LOCAL account on this host: LDAP changes will not show here "
              "until it is cleaned (nsswitch resolves 'files' before 'sss')."},
    "msg.warn.no_home": {
        "es": "El directorio home no existe en el almacenamiento compartido.",
        "en": "The home directory does not exist in the shared storage."},
    "msg.warn.primary_missing": {
        "es": "El grupo primario ({group}) no lo tiene en memberUid: `id` podría no "
              "mostrarlo.",
        "en": "Its primary group ({group}) is not in memberUid: `id` might not show "
              "it."},
    "msg.warn.no_slurm": {
        "es": "No tiene cuentas en Slurm: puede entrar pero no enviar trabajos.",
        "en": "It has no Slurm accounts: it can log in but cannot submit jobs."},

    # ---------------------------------------------------------------------
    # Deleting an account (users/deletion.py)
    # ---------------------------------------------------------------------
    "msg.home_action.invalid": {"es": "home_action inválido: {value!r}",
                                "en": "invalid home_action: {value!r}"},
    "msg.delete.home_removed": {"es": "(borrado)", "en": "(deleted)"},
    "msg.delete.local_hint": {
        "es": "Sigue existiendo una cuenta LOCAL de {username!r} en {host}. Los cambios "
              "en LDAP no se ven en ese host porque nsswitch resuelve 'files' antes que "
              "'sss'.\nPara limpiarla:\n    ssh root@<host> \"userdel {username!r}\"\n"
              "Repita la comprobación con `kutral_mgr consult {username!r}` en cada host "
              "donde aparezca.",
        "en": "A LOCAL account for {username!r} still exists on {host}. LDAP changes "
              "are not visible on that host because nsswitch resolves 'files' before "
              "'sss'.\nTo clean it:\n    ssh root@<host> \"userdel {username!r}\"\n"
              "Repeat the check with `kutral_mgr consult {username!r}` on every host "
              "where it shows up."},
    "msg.host.this": {"es": "este host", "en": "this host"},
    "msg.no_changes": {"es": "(sin cambios)", "en": "(no changes)"},
    "msg.delete.still_resolved": {
        "es": "La cuenta sigue resolviéndose por otra vía; revíselo en cada host de "
              "identidad antes de dar el borrado por hecho.",
        "en": "The account is still resolved through another path; check it on every "
              "identity host before taking the deletion as done."},

    "msg.group.case_collision": {
        "es": "Ya existe un grupo llamado {name!r} que difiere sólo en mayúsculas. LDAP "
              "compara `cn` sin distinguir mayúsculas, así que los dos serían "
              "ambiguos al buscar por nombre.",
        "en": "A group named {name!r} already exists which differs only in case. LDAP "
              "compares `cn` case-insensitively, so the two would be ambiguous when "
              "searching by name."},
    "msg.group.gid_taken": {
        "es": "El gid {gid} ya lo usa el grupo {group!r}.",
        "en": "Gid {gid} is already used by group {group!r}."},
    "msg.group.lab_kept": {
        "es": "Se conservó la carpeta {path}: puede tener datos de sus miembros.",
        "en": "The folder {path} was kept: it may hold data belonging to its members."},
    "msg.group.render.not_found": {
        "es": "No se encontró el grupo {group!r} en el directorio.",
        "en": "Group {group!r} was not found in the directory."},
    "msg.group.render.title": {"es": "GRUPO", "en": "GROUP"},
    "msg.group.render.members": {"es": "Miembros ({count})", "en": "Members ({count})"},
    "msg.group.render.none": {"es": "(ninguno)", "en": "(none)"},
    "msg.group.render.lab_folder": {"es": "Carpeta de lab", "en": "Lab folder"},
    "msg.group.render.no_folder": {"es": "(sin carpeta)", "en": "(no folder)"},
    "msg.group.render.exists": {"es": "[existe]", "en": "[exists]"},
    "msg.group.render.not_exists": {"es": "[NO EXISTE]", "en": "[DOES NOT EXIST]"},
    "msg.group.render.slurm_account": {"es": "Cuenta de Slurm", "en": "Slurm account"},
    "msg.group.render.not_checked": {"es": "(no se pudo comprobar)",
                                      "en": "(could not be checked)"},
    "msg.move.group_created": {"es": "grupo creado en LDAP (gid {gid})",
                               "en": "group created in LDAP (gid {gid})"},
    "msg.move.members_from_start": {"es": "{count} miembros desde el inicio",
                                    "en": "{count} members from the start"},
    "msg.move.identity_refreshed": {"es": "caché de identidad refrescada",
                                    "en": "identity cache refreshed"},
    "msg.move.lab_folder": {"es": "carpeta de laboratorio con setgid 2770",
                            "en": "lab folder with setgid 2770"},
    "msg.move.slurm_account_new": {"es": "cuenta de Slurm creada",
                                   "en": "Slurm account created"},
    "msg.move.members_associated": {"es": "{count} miembros asociados en Slurm",
                                    "en": "{count} members associated in Slurm"},
    "msg.group.invalid_name": {
        "es": "Nombre de grupo inválido: {value!r}. Debe empezar con letra o número y "
              "contener sólo letras, números, guion o guion bajo (2 a 31 caracteres).",
        "en": "Invalid group name: {value!r}. It must start with a letter or a digit "
              "and contain only letters, digits, hyphen or underscore (2 to 31 "
              "characters)."},
    "msg.group.member_missing": {
        "es": "El miembro {member!r} no existe en el directorio: el grupo no se crea a "
              "medias.",
        "en": "Member {member!r} does not exist in the directory: the group is not "
              "created halfway."},
    "msg.group.has_members": {
        "es": "El grupo {group!r} tiene {count} miembros ({members}). Quítelos primero "
              "con group-remove-member, o use --forzar si sabe lo que hace.",
        "en": "Group {group!r} has {count} members ({members}). Remove them first with "
              "group-remove-member, or use --force if you know what you are doing."},
    "msg.group.is_primary": {
        "es": "El grupo {group!r} es el grupo primario de {count}: {users} quedarían "
              "apuntando a un grupo que no existe. Muévalos con change-group antes de "
              "borrarlo.",
        "en": "Group {group!r} is the primary group of {count}: {users} would be left "
              "pointing at a group that does not exist. Move them with change-group "
              "before deleting it."},

    # ---------------------------------------------------------------------
    # Fields shown to the operator (creation and modification)
    # ---------------------------------------------------------------------
    "field.fullname": {"es": "Nombre completo", "en": "Full name"},
    "field.username": {"es": "Usuario", "en": "Username"},
    "field.group": {"es": "Grupo", "en": "Group"},
    "field.mail": {"es": "Correo", "en": "Mail"},
    "field.cn": {"es": "Nombre completo", "en": "Full name"},
    "field.shell": {"es": "Shell", "en": "Shell"},
    "field.employee_type": {"es": "Tipo de cuenta", "en": "Account type"},
    "field.institute": {"es": "Institución", "en": "Institution"},
    "field.course": {"es": "Curso", "en": "Course"},

    # ---------------------------------------------------------------------
    # Creating accounts
    # ---------------------------------------------------------------------
    "msg.field.missing": {"es": "Falta {field}.", "en": "Missing {field}."},
    "msg.account.exists": {"es": "La cuenta {username!r} ya existe en el directorio.",
                           "en": "The account {username!r} already exists in the "
                                 "directory."},
    "msg.creation.group_missing": {
        "es": "El grupo {group!r} no existe en el directorio. Cree el grupo antes de dar "
              "de alta a la persona (kutral_mgr group-create), o revise el nombre.",
        "en": "Group {group!r} does not exist in the directory. Create the group before "
              "creating the person (kutral_mgr group-create), or check the name."},
    "msg.creation.uid_not_number": {
        "es": "El UID debe ser un número (se recibió {value!r}).",
        "en": "The UID must be a number (received {value!r})."},
    "msg.creation.group_no_gid": {"es": "El grupo {group!r} no tiene gidNumber.",
                                  "en": "Group {group!r} has no gidNumber."},
    "msg.creation.hook_failed": {
        "es": "El hook falló: {command} ({error}).",
        "en": "The hook failed: {command} ({error})."},
    "msg.creation.hook_no_detail": {"es": "sin detalle", "en": "no detail"},
    "msg.no_detail": {"es": "sin detalle", "en": "no detail"},

    # ---------------------------------------------------------------------
    # Deleting, reactivating
    # ---------------------------------------------------------------------
    "msg.delete.simulated": {
        "es": "Se borraría {username!r} de {groups} grupos y de LDAP (simulación).",
        "en": "{username!r} would be deleted from {groups} groups and from LDAP "
              "(simulation)."},
    "msg.delete.done": {"es": "Cuenta {username!r} borrada del directorio.",
                        "en": "Account {username!r} deleted from the directory."},
    "msg.reactivate.slurm_warning": {
        "es": "La cuenta quedó reactivada en el directorio, pero Slurm no pudo restaurar "
              "sus laboratorios: {error}",
        "en": "The account was reactivated in the directory, but Slurm could not "
              "restore its labs: {error}"},

    # ---------------------------------------------------------------------
    # Modifying accounts
    # ---------------------------------------------------------------------
    "msg.group.not_found.under": {
        "es": "El grupo {group!r} no existe bajo {base}.\n"
              "Ojo: si el grupo está colgado de la raíz en vez de ou=Group (en el "
              "clúster real hay uno así, cn=lab-diez), no se encuentra buscando "
              "por nombre de grupo.",
        "en": "Group {group!r} does not exist under {base}.\n"
              "Note: if the group hangs from the root instead of ou=Group (the real "
              "cluster has one like that, cn=lab-diez), it will not be found by "
              "searching for a group name."},
    "msg.modify.nothing_to_do": {"es": "No hay cambios que aplicar.",
                                 "en": "There are no changes to apply."},
    "msg.modify.use_change_group": {
        "es": "Para cambiar el grupo use change_group (mueve gidNumber, memberUid y "
              "departmentNumber juntos). Cambiar sólo departmentNumber dejaría la cuenta "
              "mintiendo sobre su grupo.",
        "en": "To change the group use change_group (it moves gidNumber, memberUid and "
              "departmentNumber together). Changing only departmentNumber would leave "
              "the account lying about its group."},
    "msg.modify.attribute_not_editable": {
        "es": "El atributo {attribute!r} no es editable desde acá. Editables: {editable}.",
        "en": "Attribute {attribute!r} is not editable from here. Editable: {editable}."},
    "msg.modify.empty_value": {"es": "El valor de {field} no puede quedar vacío.",
                               "en": "The value of {field} cannot be empty."},
    "msg.modify.shell_absolute": {
        "es": "El shell debe ser una ruta absoluta (ej. /bin/bash).",
        "en": "The shell must be an absolute path (e.g. /bin/bash)."},
    "msg.modify.identical": {"es": "Los valores enviados son idénticos a los actuales.",
                             "en": "The values sent are identical to the current ones."},
    "msg.modify.primary_group": {
        "es": "El grupo {group!r} es el grupo primario de {username} (gidNumber). Para "
              "sacarlo de ese grupo hay que moverlo a otro con change-group.",
        "en": "Group {group!r} is the primary group of {username} (gidNumber). To take "
              "them out of that group, move them to another one with change-group."},
    "msg.modify.slurm_warning": {
        "es": "El cambio en el directorio quedó hecho, pero Slurm no pudo reasociar a "
              "{group}: {error}",
        "en": "The change in the directory was made, but Slurm could not reassociate "
              "to {group}: {error}"},

    # ---------------------------------------------------------------------
    # Steps recorded in the audit trail and shown in --json
    # ---------------------------------------------------------------------
    "msg.move.ldap_created": {"es": "cuenta creada en LDAP",
                              "en": "account created in LDAP"},
    "msg.move.member_added": {"es": "agregado al grupo {group}",
                              "en": "added to group {group}"},
    "msg.move.member_added_to": {"es": "agregado a {group}", "en": "added to {group}"},
    "msg.move.member_removed_from": {"es": "quitado de {group}",
                                      "en": "removed from {group}"},
    "msg.move.home_created": {"es": "home, enlace de laboratorio e historial creados",
                              "en": "home, lab link and history created"},
    "msg.move.slurm_account_created": {"es": "cuenta de Slurm {group} creada",
                                        "en": "Slurm account {group} created"},
    "msg.move.slurm_associated": {"es": "asociado a la cuenta {group}",
                                  "en": "associated with account {group}"},
    "msg.change.group_field": {"es": "Grupo (gidNumber)", "en": "Group (gidNumber)"},
    "msg.change.secondary_groups": {"es": "Grupos secundarios",
                                    "en": "Secondary groups"},

    # ---------------------------------------------------------------------
    # Ports and adapters
    # ---------------------------------------------------------------------
    "msg.port.missing": {
        "es": "El puerto '{name}' no está configurado en este entorno. Revise cómo se "
              "armó el Environment.",
        "en": "Port '{name}' is not configured in this environment. Check how the "
              "Environment was built."},
    "msg.directory.entry_unreadable": {"es": "No se pudo leer la entrada {entry}: {error}",
                                      "en": "Could not read entry {entry}: {error}"},
    "msg.directory.connect_failed": {
        "es": "No se pudo conectar a {server} como {user}: {error}",
        "en": "Could not connect to {server} as {user}: {error}"},
    "msg.directory.search_failed": {
        "es": "Fallo la búsqueda {search} en {base}: {error}",
        "en": "Search {search} in {base} failed: {error}"},
    "msg.directory.rejected": {
        "es": "LDAP rechazó la operación sobre {dn}: {error}",
        "en": "LDAP rejected the operation on {dn}: {error}"},
    "msg.directory.needs_uid": {"es": "create_user necesita 'uid'.",
                               "en": "create_user needs 'uid'."},
    "msg.directory.group_exists": {
        "es": "El grupo {group!r} ya existe en el directorio.",
        "en": "Group {group!r} already exists in the directory."},
    "msg.directory.rename_failed": {
        "es": "No se pudo renombrar {dn} a uid={uid}: {error}",
        "en": "Could not rename {dn} to uid={uid}: {error}"},
    "msg.directory.backup_missing": {
        "es": "No se pudo respaldar {dn}: la entrada no se encontró.",
        "en": "Could not back up {dn}: the entry was not found."},
    "msg.directory.no_backups_dir": {"es": "No hay backups_dir configurado.",
                                     "en": "No backups_dir is configured."},
    "msg.seed.header": {"es": "# Seed sintético del Centro de Control Kutral",
                        "en": "# Kutral Control Center synthetic seed"},
    "msg.seed.generated": {
        "es": "# Generado automáticamente: NO contiene datos reales.",
        "en": "# Generated automatically: it contains NO real data."},
    "msg.directory.backup_header": {
        "es": "# Respaldo previo a una modificación del Centro de Control",
        "en": "# Backup taken before a change by the Kutral Control Center"},
    "msg.directory.retired_uid_failed": {
        "es": "No se pudo anotar el uid {uid} como retirado: {error}",
        "en": "Could not record uid {uid} as retired: {error}"},
    "msg.slurm.command_failed": {"es": "sacctmgr falló ({command}): {error}",
                                 "en": "sacctmgr failed ({command}): {error}"},
    "msg.slurm.account_delete_failed": {
        "es": "No se pudo borrar la cuenta de Slurm {account!r}: {error}",
        "en": "Could not delete the Slurm account {account!r}: {error}"},
    "msg.slurm.user_remove_failed": {
        "es": "No se pudo quitar a {username!r} de Slurm: {error}",
        "en": "Could not remove {username!r} from Slurm: {error}"},
    "msg.slurm.no_backup": {
        "es": "No hay respaldo de Slurm para {username!r}: se usó la cuenta por defecto "
              "{account!r}. Si no corresponde, corríjalo con change-group o "
              "group-add-member.",
        "en": "There is no Slurm backup for {username!r}: the default account "
              "{account!r} was used. If that is wrong, fix it with change-group or "
              "group-add-member."},
    "msg.storage.chown_failed": {
        "es": "No se pudo asignar dueño a {path} (uid={uid}, gid={gid}): {error}",
        "en": "Could not set the owner of {path} (uid={uid}, gid={gid}): {error}"},
    "msg.storage.chmod_failed": {
        "es": "No se pudo fijar el modo {mode} en {path}: {error}",
        "en": "Could not set mode {mode} on {path}: {error}"},
    "msg.storage.history_move_failed": {
        "es": "No se pudo mover la carpeta del historial {origin} a {destination}: {error}",
        "en": "Could not move the history folder {origin} to {destination}: {error}"},
    "msg.storage.outside_bases": {
        "es": "Por seguridad no se toca {path!r}: está fuera de {home} y {labs}.",
        "en": "For safety, {path!r} is not touched: it is outside {home} and "
              "{labs}."},
    "msg.storage.never_delete_base": {
        "es": "Por seguridad no se borra la base completa {path!r}.",
        "en": "For safety, the whole base {path!r} is not deleted."},
    "msg.storage.home_exists": {
        "es": "No se mueve el home: {path} ya existe.",
        "en": "The home is not moved: {path} already exists."},
    "msg.storage.action.link": {"es": "enlace {path}", "en": "link {path}"},
    "msg.storage.action.history": {"es": "historial {path}",
                                  "en": "history {path}"},
    "msg.storage.action.history_moved": {"es": "historial {origin} -> {destination}",
                                        "en": "history {origin} -> {destination}"},
    "msg.storage.history_exists": {
        "es": "Ya existía {destination}: se conserva, y {origin} queda como estaba.",
        "en": "{destination} already existed: it is kept, and {origin} is left as it "
              "was."},
    "msg.identity.refresh_failed": {
        "es": "No se pudo refrescar la caché de identidad ({command}): {error}",
        "en": "Could not refresh the identity cache ({command}): {error}"},
    "msg.audit.insecure_permissions": {
        "es": "El archivo {path} tiene permisos {mode} (debería ser 600).",
        "en": "File {path} has permissions {mode} (it should be 600)."},
    "msg.audit.chmod_hint": {"es": "Sugerencia: chmod 600 {path}",
                             "en": "Hint: chmod 600 {path}"},
    "msg.audit.write_failed": {"es": "No se pudo escribir el registro de auditoría: {error}",
                               "en": "Could not write the audit record: {error}"},
    "msg.run.binary_missing": {
        "es": "no se encontró el ejecutable {name!r}",
        "en": "the executable {name!r} was not found"},
    "msg.group.shared_gid": {
        "es": "{names} (gid {gid} compartido)",
        "en": "{names} (gid {gid} shared)"},
    "msg.run.timeout": {
        "es": "el comando no terminó en {seconds}s",
        "en": "the command did not finish within {seconds}s"},
    "msg.hooks.missing_context": {
        "es": "el comando pide {name!r} y no está disponible",
        "en": "the command asks for {name!r} and it is not available"},
    "msg.hooks.timeout": {"es": "no terminó en {seconds}s",
                          "en": "it did not finish within {seconds}s"},
    "msg.audit.operator_unknown": {"es": "desconocido", "en": "unknown"},
    "msg.audit.redacted": {"es": "***REDACTADO***", "en": "***REDACTED***"},
    "msg.hooks.temp_delete_failed": {
        "es": "Aviso: no se pudo borrar el archivo temporal {path}: {error}",
        "en": "Warning: could not delete the temporary file {path}: {error}"},

    # ---------------------------------------------------------------------
    # Mail: the transport and the diagnostics (the mails themselves are at the end)
    # ---------------------------------------------------------------------
    "msg.mail.unknown_kind": {"es": "Tipo de correo desconocido: {kind!r}",
                            "en": "Unknown mail kind: {kind!r}"},
    "msg.mail.missing_context": {
        "es": "Correo {kind} sin datos obligatorios: {missing}",
        "en": "Mail {kind} without the required data: {missing}"},
    "msg.mail.prepare_failed": {"es": "No se pudo preparar el correo: {error}",
                                "en": "Could not prepare the mail: {error}"},
    "msg.mail.tutorial_missing": {
        "es": "Aviso: no se encontró el tutorial en {path!r}; el correo va sin adjunto.",
        "en": "Warning: the tutorial was not found at {path!r}; the mail goes out with "
              "no attachment."},
    "msg.mail.attach_failed": {"es": "Aviso: no se pudo adjuntar {path!r}: {error}",
                               "en": "Warning: could not attach {path!r}: {error}"},
    "msg.mail.unknown_transport": {
        "es": "Transporte de correo desconocido: {transport!r}",
        "en": "Unknown mail transport: {transport!r}"},
    "msg.mail.msmtp_missing": {
        "es": "Aviso: no se encontró el binario 'msmtp' en este host.",
        "en": "Warning: the 'msmtp' binary was not found on this host."},
    "msg.mail.msmtp_failed": {"es": "msmtp falló al enviar a {to}: {error}",
                              "en": "msmtp failed sending to {to}: {error}"},
    "msg.mail.smtp_failed": {
        "es": "SMTP falló al enviar a {to} ({server}:{port}): {error}",
        "en": "SMTP failed sending to {to} ({server}:{port}): {error}"},
    "msg.mail.file_failed": {"es": "No se pudo escribir el correo en {outdir}: {error}",
                             "en": "Could not write the mail into {outdir}: {error}"},

    # ---------------------------------------------------------------------
    # The fake directory (test double)
    # ---------------------------------------------------------------------
    "msg.group.not_found.short": {"es": "El grupo {group!r} no existe.",
                                  "en": "Group {group!r} does not exist."},
    "msg.account.exists.short": {"es": "La cuenta {username!r} ya existe.",
                                 "en": "Account {username!r} already exists."},
    "msg.group.exists.short": {"es": "El grupo {group!r} ya existe.",
                               "en": "Group {group!r} already exists."},
    "msg.not_found.short": {"es": "No existe {dn}.", "en": "{dn} does not exist."},
    "msg.attribute.missing_for_delete": {
        "es": "El atributo '{attribute}' no existe en {dn} (no hay nada que quitar).",
        "en": "Attribute '{attribute}' does not exist in {dn} (there is nothing to "
              "remove)."},
    "msg.backup_failed.short": {"es": "No se pudo respaldar {dn}.",
                                "en": "Could not back up {dn}."},

    "msg.env.no_sacctmgr": {
        "es": "Este comando necesita `sacctmgr` y no está disponible en este host.\n"
              "Ejecútelo desde el nodo de gestión, donde Slurm está instalado, o use\n"
              "--config config.lab.yaml para recorrerlo en ensayo sin tocar el clúster.",
        "en": "This command needs `sacctmgr` and it is not available on this host.\n"
              "Run it from the management node, where Slurm is installed, or use\n"
              "--config config.lab.yaml to walk it through in rehearsal without "
              "touching the cluster."},

    # ---------------------------------------------------------------------
    # The mails that reach a person, in their two languages
    # ---------------------------------------------------------------------
    # They follow the language of the run, like everything else. The keys are grouped by
    # the part of the mail they fill, so that reusing a heading in two mails does not
    # duplicate its translation.
    "mail.plain.alternative": {
        "es": "Su cliente de correo no soporta mensajes HTML.",
        "en": "Your mail client does not support HTML messages."},
    "mail.footer.signature": {"es": "Atentamente,", "en": "Sincerely,"},
    "mail.footer.team": {
        "es": "Equipo de Administración de Sistemas Clúster {cluster}",
        "en": "Cluster System Administration Team {cluster}"},
    "mail.greeting": {"es": "Estimado/a <b>{username}</b>,",
                      "en": "Dear <b>{username}</b>,"},
    "mail.section.credentials": {"es": "Credenciales de Acceso",
                                 "en": "Access Credentials"},
    "mail.section.links": {"es": "Enlaces y Servicios", "en": "Links and Services"},
    "mail.section.paths": {"es": "Rutas de Trabajo", "en": "Working Paths"},
    "mail.field.username": {"es": "Usuario", "en": "Username"},
    "mail.field.password": {"es": "Contraseña", "en": "Password"},
    "mail.field.temp_password": {"es": "Contraseña temporal",
                                 "en": "Temporary password"},
    "mail.field.ssh": {"es": "Acceso SSH", "en": "SSH access"},
    "mail.field.home": {"es": "Directorio Home", "en": "Home directory"},
    "mail.field.lab_folder": {"es": "Carpeta de Lab", "en": "Lab folder"},
    "mail.value.no_group": {"es": "(su grupo)", "en": "(your group)"},
    "mail.value.empty": {"es": "(vacío)", "en": "(empty)"},
    "mail.link.web": {"es": "Plataforma Web", "en": "Web Platform"},
    "mail.link.documentation": {"es": "Documentación", "en": "Documentation"},

    # Common blocks: remote access and the temporary-password notice.
    "mail.section.remote_access": {"es": "Acceso Remoto", "en": "Remote Access"},
    "mail.remote_access.vpn": {
        "es": "Desde fuera del campus es obligatorio usar la VPN institucional. Con "
              "correo institucional, gestione el acceso en la "
              '<a href="https://mesa.servicios.ejemplo.cl">Mesa de Servicios</a> de DTI.',
        "en": "From outside the campus the institutional VPN is mandatory. With an "
              "institutional mail address, request access at the DTI "
              '<a href="https://mesa.servicios.ejemplo.cl">Service Desk</a>.'},
    "mail.remote_access.external": {
        "es": "Si es usuario externo, el acceso remoto se coordina con la administración "
              "del clúster.",
        "en": "If you are an external user, remote access is arranged with the cluster "
              "administration."},
    "mail.temp_password.notice": {
        "es": "Es una contraseña <b>temporal</b>: cámbiela en su primer ingreso con el "
              "comando <b>passwd</b>. La cuenta es personal e intransferible. Para más "
              "información, lea el instructivo adjunto.",
        "en": "It is a <b>temporary</b> password: change it on your first login with the "
              "<b>passwd</b> command. The account is personal and non-transferable. For "
              "more information, read the attached guide."},
    "mail.temp_password.notice.reset": {
        "es": "Es una contraseña <b>temporal</b>: cámbiela en su primer ingreso con el "
              "comando <b>passwd</b>. La contraseña anterior ya no funciona. "
              "Para más información, lea el instructivo adjunto.",
        "en": "It is a <b>temporary</b> password: change it on your first login with the "
              "<b>passwd</b> command. The previous password no longer works. For more "
              "information, read the attached guide."},

    # 1. Creation.
    "mail.welcome.subject": {"es": "Credenciales de Acceso - Clúster {cluster}",
                             "en": "Access Credentials - {cluster} Cluster"},
    "mail.welcome.intro": {
        "es": "Le damos la bienvenida al Clúster {cluster} de la Universidad de "
              "O'Higgins. Su cuenta ha sido habilitada exitosamente.",
        "en": "Welcome to the {cluster} Cluster of Universidad de O'Higgins. Your "
              "account has been enabled successfully."},
    "mail.welcome.section.practices": {"es": "Buenas Prácticas",
                                       "en": "Good Practices"},
    "mail.welcome.practice.credentials": {
        "es": "Mantenga la confidencialidad de sus credenciales.",
        "en": "Keep your credentials confidential."},
    "mail.welcome.practice.load": {
        "es": "No ejecute procesos de alta carga en el nodo de login: use Slurm.",
        "en": "Do not run heavy processes on the login node: use Slurm."},
    "mail.welcome.practice.editors": {
        "es": "No conecte editores externos directamente al nodo de login.",
        "en": "Do not connect external editors directly to the login node."},
    "mail.welcome.practice.tutorial": {
        "es": 'Revise el documento adjunto <i>"Tutorial_basico_uso_cluster.pdf"</i>.',
        "en": 'Read the attached document <i>"Tutorial_basico_uso_cluster.pdf"</i>.'},

    # 2. Modification.
    "mail.modification.subject": {"es": "Actualización de su Cuenta - Clúster {cluster}",
                                  "en": "Your Account Was Updated - {cluster} Cluster"},
    "mail.modification.intro": {
        "es": "Le informamos que su cuenta en el Clúster {cluster} fue actualizada.",
        "en": "We inform you that your account on the {cluster} Cluster was updated."},
    "mail.modification.section.changes": {"es": "Cambios Aplicados",
                                          "en": "Changes Applied"},
    "mail.modification.no_changes": {"es": "Sin cambios de atributos.",
                                     "en": "No attribute changes."},
    "mail.modification.row.before": {"es": "{label} (antes)",
                                     "en": "{label} (before)"},
    "mail.modification.row.after": {"es": "{label} (ahora)",
                                    "en": "{label} (after)"},
    "mail.modification.section.password": {"es": "Contraseña", "en": "Password"},
    "mail.modification.password_changed": {
        "es": "Su contraseña fue cambiada en esta misma operación; le llega por su "
              "propio correo, junto con el usuario y el acceso.",
        "en": "Your password was changed in this same operation; it arrives in its own "
              "mail, together with the username and the access details."},
    "mail.modification.password_untouched": {
        "es": "Su contraseña no fue modificada.",
        "en": "Your password was not changed."},

    # 3. Reset: the temporary password travels in the mail that announces it.
    "mail.password.subject": {"es": "Contraseña restablecida - Clúster {cluster}",
                              "en": "Password Reset - {cluster} Cluster"},
    "mail.password.intro": {
        "es": "Su contraseña en el Clúster {cluster} fue restablecida.",
        "en": "Your password on the {cluster} Cluster has been reset."},

    # 4. Suspension.
    "mail.deactivation.subject": {
        "es": "Aviso de Suspensión de Cuenta - Clúster {cluster}",
        "en": "Account Suspension Notice - {cluster} Cluster"},
    "mail.deactivation.intro": {
        "es": "Le informamos que su cuenta en el Clúster {cluster} ha sido suspendida.",
        "en": "We inform you that your account on the {cluster} Cluster has been "
              "suspended."},
    "mail.deactivation.state": {
        "es": "<b>Estado actual:</b> el acceso remoto por SSH y la ejecución de tareas "
              "en Slurm quedan suspendidos. Sus archivos se conservan.",
        "en": "<b>Current state:</b> remote SSH access and job execution on Slurm are "
              "suspended. Your files are kept."},
    "mail.deactivation.section.reason": {"es": "Motivo", "en": "Reason"},
    "mail.deactivation.default_reason": {
        "es": "Fin de proyecto, curso o periodo académico, o revisión administrativa.",
        "en": "End of a project, course or academic period, or an administrative "
              "review."},
    "mail.deactivation.section.next_steps": {"es": "¿Qué debe hacer?",
                                            "en": "What should you do?"},
    "mail.deactivation.next_steps": {
        "es": "Si requiere una aclaración o solicitar la reactivación, contacte a la "
              "administración del clúster.",
        "en": "If you need clarification or want to request reactivation, contact the "
              "cluster administration."},

    # 5. Reactivation.
    "mail.reactivation.subject": {"es": "Cuenta Reactivada - Clúster {cluster}",
                                  "en": "Account Reactivated - {cluster} Cluster"},
    "mail.reactivation.intro": {
        "es": "Su cuenta en el Clúster {cluster} ha sido <b>reactivada</b>. Sus servicios "
              "están operativos nuevamente.",
        "en": "Your account on the {cluster} Cluster has been <b>reactivated</b>. Your "
              "services are operational again."},
    "mail.reactivation.password_unchanged": {
        "es": "(la actual, sin cambios)",
        "en": "(the current one, unchanged)"},
    "mail.reactivation.section.validity": {"es": "Vigencia", "en": "Validity"},
    "mail.reactivation.until": {
        "es": "Su cuenta está activa hasta el <b>{expires}</b>.",
        "en": "Your account is active until <b>{expires}</b>."},
    "mail.reactivation.forever": {
        "es": "Su cuenta queda activa sin fecha de vencimiento.",
        "en": "Your account stays active with no expiry date."},
}
