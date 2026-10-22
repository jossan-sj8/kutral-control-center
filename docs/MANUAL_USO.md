# User manual — Kutral Control Center

This manual is for whoever operates the cluster. It describes the 20 commands, what each
one does and —most importantly— **how to check from the outside** that it did what it says
it did.

That last part is not decoration: the tool says "done", but what confirms it is
`ldapsearch`, `getent`, `sacctmgr` or `ls -ld`. Never take an operation for granted on the
strength of the tool's own output.

This file is the English edition of the manual. Both editions describe the same tool; the
tool itself can be operated in either language (see `--lang` / `--idioma` below).

## Before you start

```bash
cd /root/kutral-control-center
venv/bin/python kutral_mgr.py --help
```

Every example uses `venv/bin/python kutral_mgr.py`. If you prefer, create an alias:

```bash
alias cc='/root/kutral-control-center/venv/bin/python /root/kutral-control-center/kutral_mgr.py'
```

## Global flags

They work **before or after** the subcommand, in any order.

| Flag | What it does |
|---|---|
| `--config PATH` | configuration file. Defaults to `config.yaml` (production) |
| `--simulate` | walks the whole flow **without writing anything** and without sending mail |
| `--json` | JSON output, for automation |
| `--yes` | asks nothing: it uses only what comes in as a parameter. The directory password is the only exception: if it is not exported and there is a terminal, it is asked for once; in a script with no terminal it fails on the spot |
| `--lang`, `--idioma` | language of the run: `es` or `en`. Also set by the `KUTRAL_LANG` environment variable, and otherwise taken from the machine's locale |
| `--enviar-correo` | forces sending the mail |
| `--no-enviar-correo` | prevents it |
| `--sin-cabecera` | does not print the environment header (the SIMULATION notice is printed anyway) |

Commands **and flags** have a spelling in both languages: `create-user` or `crear-usuario`,
`--full-name` or `--nombre-completo`, `--simulate` or `--simular`, `--yes` or `--si`. The
Control Center is operated the same way in Spanish or in English, and `kutral_mgr.py --help`
lists both spellings.

Three notes that save surprises:

- **`--simulate` is not a "read-only mode".** It runs the real flow with the real adapters
  (so it really does read LDAP and Slurm) and only skips the writes: it is there to show
  which LDAP changes it would make and which Slurm associations it is counting on. It does
  not print the `sacctmgr` calls it would run, because in simulation those calls are
  skipped entirely.
- **`--enviar-correo` is not the default.** If `cluster.send_mail` is `ask` and you are on
  an interactive terminal, it asks; with no terminal (a script, a cron job) it sends
  nothing.
- **The session uses the expiry policy from the configuration.** See below.

---

## 1. Read-only commands

They write nothing. They are the only ones that can be used at any time without risk.

### `status`

Summary of the directory: how many accounts, how many groups, how they break down by
state, and which adapters are in use.

```bash
venv/bin/python kutral_mgr.py status
venv/bin/python kutral_mgr.py status --json
```

**Check from the outside:**

```bash
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=People,<SUFIJO_DEL_DIRECTORIO>" \
  "(objectClass=posixAccount)" uid | grep -c '^uid:'
```

The two numbers have to match. If they do not, something is off in the filter or in the
connection.

### `consult [term]`

Searches by exact username, partial username, name, mail or account type, and shows
everything known about that person: LDAP, state, groups, Slurm accounts, whether the home
exists and whether they have a local account on the host.

```bash
venv/bin/python kutral_mgr.py consult un-usuario
venv/bin/python kutral_mgr.py consult "Usuario"
venv/bin/python kutral_mgr.py consult otro-usuario --json
```

Besides the data, it shows **warnings** when something does not add up:

```
------------------------------------------------------------------
  [!] Tiene cuenta LOCAL en este host: los cambios en LDAP no se verán aquí
      hasta limpiarla (nsswitch resuelve 'files' antes que 'sss').
```

That warning is the on-screen explanation of why a change made in LDAP "does not show" on
a host. When it appears, clean up the local copy on that host (`userdel`) before promising
anybody anything.

**Check from the outside:** compare against

```bash
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=People,<SUFIJO_DEL_DIRECTORIO>" "(uid=un-usuario)"
sacctmgr show assoc user=un-usuario
getent passwd un-usuario
```

### `export`

Writes an Excel file with three sheets (`Todos`, `Activos`, `Bloqueados` in Spanish; `All`,
`Active`, `Blocked` in English), in the same format as the historical reports, so they can
be compared directly.

```bash
venv/bin/python kutral_mgr.py export
venv/bin/python kutral_mgr.py export --output /tmp/roll.xlsx
```

**Check from the outside:** open the file and compare the totals against `status`. If you
have just created users by hand, this is the quickest way to see **how they came out**:
without `departmentNumber`, with `sn` holding the full name, without `mail`, without a
Slurm account.

### `verify`

Diagnostics: which adapters are in use, whether the directory answers and how many entries
it sees.

```bash
venv/bin/python kutral_mgr.py verify
```

It is the first command worth running on a new host.

---

## 2. User commands

### `create-user` — create an account

The temporary password is 8 characters long and uses only symbols that break nothing:
`- _ . @ + =`. No `$`, `&`, `!`, `#`, `*` or parentheses: that way it can be dictated,
copied or pasted on a command line with no quoting and no escapes.

| Flag | |
|---|---|
| `--full-name` | full name (required) |
| `--username` | username (required; one is suggested if you do not give it). 3 to 11 characters: lowercase, digits, dot, hyphen and underscore |
| `--group` | primary group (required; it **must exist**) |
| `--mail` | mail (required; that is where the credentials go) |
| `--employee-type`, `--institute`, `--course` | optional |
| `--expires` | expiry: see the table of forms below |

Without `--yes` it asks for whatever is missing, and proposes a username in the cluster's
style (first initial + surname: "Otro Usuario" → `otro-usuario`).

- The **group is typed**, not picked from a list. It has to exist: if it does not, it offers
  to create it right there with the next free gid, its laboratory folder and its Slurm
  account.
- Before writing anything it shows a **summary** (username, group, mail, uid/gid, expiry)
  and asks for confirmation. With `--yes` there is no summary and no questions.

```bash
venv/bin/python kutral_mgr.py create-user \
  --full-name "Otro Usuario" --username otro-usuario \
  --group lab-uno --mail otro.usuario@ejemplo.cl \
  --employee-type student --institute UOH
```

**The interactive form:** with no flags, the tool asks only for what is missing and shows a
summary before writing anything. Flags that are already set **are not asked about**, so the
two can be mixed (for instance, fix the group and let it ask for the rest):

```bash
venv/bin/python kutral_mgr.py create-user
```

```
Nombre completo: Otro Usuario
Usuario [otro-usuario]: 
Grupo del usuario: lab-uno
Correo: otro.usuario@ejemplo.cl
Tipo de cuenta [student]: 
Institución [UOH]: 
Curso (opcional): 
¿Enviar el correo de bienvenida? [s/N]: n
============================================================
  RESUMEN DE LA CUENTA
============================================================
 Nombre completo     : Otro Usuario
 Usuario             : otro-usuario
 Grupo primario      : lab-uno (gid 9013)
 Correo              : otro.usuario@ejemplo.cl
 Tipo de cuenta      : student
 Institución         : UOH
 Curso               : -
 Vencimiento         : sin vencimiento
 uid / gid           : 1284 / 9000
 ¿Avisar por correo? : no
============================================================
¿Crear la cuenta así? [s/N]: s
```

(The prompts are in the language of the run: in English the same questions read
`Full name:`, `Username [otro-usuario]:`, `Group:`, `Mail:`, and so on.)

Three details of the assistant:

- If the group does not exist, it **warns and offers to create it** in the same step
  (directory entry, laboratory folder with setgid and Slurm account).
- The summary shows the **already resolved uid and gid**: it is the last net before writing
  into the directory, which has no replica.
- `q` (or `quit`, `exit`, `cancelar`, `salir`) and Ctrl+C **cancel** without writing
  anything; with `--yes` there are no questions and no summary.

What it does, in order:

1. validates everything **before touching anything**
2. creates the LDAP entry, with the temporary password hashed (`{CRYPT}$6$…`)
3. adds it to its group's `memberUid`
4. creates the home on BeeGFS (750) and the link to the laboratory
5. refreshes the identity cache
6. associates it with its group's Slurm account
7. runs the configured hooks (if any)
8. sends the welcome mail, when that applies
9. leaves a record in the audit log

At the end it **prints the temporary password**: that is the only moment it exists outside
the directory. Copy it, or confirm that the mail went out.

**Check from the outside:**

```bash
getent passwd otro-usuario
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=People,<SUFIJO_DEL_DIRECTORIO>" "(uid=otro-usuario)" \
  cn sn givenName gecos uidNumber gidNumber departmentNumber loginShell shadowExpire
ls -ld /mnt/beegfs/home/otro-usuario
sacctmgr show assoc user=otro-usuario
```

And the definitive test: `ssh otro-usuario@198.51.100.104` with the password it printed.

### `modify-user` — change the data of an account

| Flag | Field |
|---|---|
| `--full-name` | full name (`cn`) |
| `--mail` | mail |
| `--shell` | login shell |
| `--employee-type` | account type |
| `--institute` | institution (`o`) |
| `--course` | course (`description`) |
| `--group` | **changes group** (same as `change-group`) |

With no flags and a terminal, it opens a menu to choose what to modify, showing the current
value as the proposal. It sends **a single mail** with the list of changes, not one per
field.

```bash
venv/bin/python kutral_mgr.py modify-user otro-usuario --mail nuevo@ejemplo.cl --employee-type postdoc
venv/bin/python kutral_mgr.py modify-user otro-usuario          # interactive menu
```

**Check from the outside:** `ldapsearch` of the attribute, and `consult` to see before and
after.

### `change-group` — move a person to another laboratory

This is the command that repairs the original problem: it moves the group in **all four
places** where it lives.

```bash
venv/bin/python kutral_mgr.py change-group otro-usuario lab-dos
venv/bin/python kutral_mgr.py change-group otro-usuario lab-dos --keep-old
```

| `--keep-old` | Leaves the previous group as a secondary membership instead of removing it. |
|---|---|

What it moves:

| Where | What |
|---|---|
| the account | `gidNumber` (primary group) |
| the new group | adds it to `memberUid` |
| the old group | removes it from `memberUid` (unless `--keep-old`) |
| the account | `departmentNumber` (the group label) |
| Slurm | re-associates the default account; **keeps** the other associations |

When it finishes, it **re-reads the directory and verifies** that all three values landed.
If something does not match, it says so.

**Check from the outside:**

```bash
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=People,<SUFIJO_DEL_DIRECTORIO>" "(uid=otro-usuario)" \
  gidNumber departmentNumber
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=Group,<SUFIJO_DEL_DIRECTORIO>" \
  "(cn=lab-dos)" memberUid
sacctmgr show assoc user=otro-usuario
id otro-usuario          # on a node, to see the effective group
```

What it does **not** do: reassign the owner of the files that already exist in the home.
They keep the previous gid.

### `add-member` / `remove-member` — secondary membership

```bash
venv/bin/python kutral_mgr.py add-member otro-usuario lab-tres
venv/bin/python kutral_mgr.py remove-member otro-usuario lab-tres
```

`remove-member` **refuses** when the group is the person's primary one: removing them from
`memberUid` would not change their `gidNumber` and would leave them in an incoherent state.
That is what `change-group` is for.

### `rename-user` — change the username

It is the most fragile operation, because the uid is written in four places.

```bash
venv/bin/python kutral_mgr.py rename-user otro-usuario otro-usuario2
venv/bin/python kutral_mgr.py rename-user otro-usuario otro-usuario2 --keep-home
```

It moves the DN, the `memberUid` of **every** group, the Slurm account (with its accounts)
and the home directory. It shows the four movements.

**Check from the outside:**

```bash
getent passwd otro-usuario2
ls -ld /mnt/beegfs/home/otro-usuario2        # and the old one must no longer exist
```

### `deactivate` — suspend an account

```bash
venv/bin/python kutral_mgr.py deactivate otro-usuario --reason "fin de semestre"
venv/bin/python kutral_mgr.py deactivate otro-usuario --keep-slurm
```

It writes **both** block markers (`shadowExpire: 1` and `/sbin/nologin`), which is the
state the blocked accounts on the cluster already have. Before removing the Slurm
associations it **backs them up on disk**, so that reactivating later brings back every
account and not only the primary one.

If the account was already blocked, it does nothing and says so.

**Check from the outside:**

```bash
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=People,<SUFIJO_DEL_DIRECTORIO>" \
  "(uid=otro-usuario)" shadowExpire loginShell
ssh otro-usuario@198.51.100.104          # it has to fail
sacctmgr -n -P show assoc user=otro-usuario format=Account   # and the backup must exist
ls -l /root/kutral-backups/slurm/otro-usuario-*.json
```

### `reactivate` — reactivate an account

```bash
venv/bin/python kutral_mgr.py reactivate otro-usuario --expires fin-de-anio
venv/bin/python kutral_mgr.py reactivate otro-usuario --expires 2028-06-30
venv/bin/python kutral_mgr.py reactivate otro-usuario --keep-password
```

It does four things: restores the shell, writes the expiry date, **generates a new
temporary password** (and prints it), and re-associates the account in Slurm — restoring the
accounts that were backed up at deactivation time.

If you only want to reactivate without touching the password: `--keep-password`.

**Check from the outside:**

```bash
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=People,<SUFIJO_DEL_DIRECTORIO>" \
  "(uid=otro-usuario)" shadowExpire loginShell
sacctmgr show assoc user=otro-usuario
ssh otro-usuario@198.51.100.104          # with the new password: it has to get in
```

### `reset-password` — generate a new temporary password

```bash
venv/bin/python kutral_mgr.py reset-password otro-usuario
venv/bin/python kutral_mgr.py reset-password otro-usuario --enviar-correo
```

It prints the password and stores the hash. The previous password **cannot be recovered**
(it is hashed): this is a reset, not a lookup.

### `expire-set` — change the expiry date of several accounts

```bash
# the 7 that expire on 2027-01-01 become permanent
venv/bin/python kutral_mgr.py expire-set nunca septimo-usuario octavo-usuario noveno-usuario

# or from a list, which is how big lists are handled
venv/bin/python kutral_mgr.py expire-set fin-de-anio --file /root/por-vencer.txt

# and it can always be rehearsed first
venv/bin/python kutral_mgr.py --simulate expire-set 2027-12-31 --file /root/lista.txt
```

It accepts the same forms as `--expires`: `nunca`, `2028-12-31`, `fin-de-anio` or a duration
(`2a`, `18m`, `90d`). The file carries **one username per line**; empty lines and lines
starting with `#` are ignored.

It is the only command that moves the date **without touching anything else**: it does not
rotate the password, does not change the shell and does not touch Slurm. `reactivate` does
all of that, and that is why it is no good for moving 7 dates.

Every account leaves behind its rollback LDIF and its audit line, and at the end it reports
how many were changed, how many already had that date and which ones do not exist.

**Check from the outside:** `ldapsearch` of the `shadowExpire` of three of them.

### `delete-user` — delete an account

```bash
venv/bin/python kutral_mgr.py delete-user otro-usuario                  # keeps the home
venv/bin/python kutral_mgr.py delete-user otro-usuario --archive-home   # archives it first
venv/bin/python kutral_mgr.py delete-user otro-usuario --delete-home    # deletes it
```

What it does: removes the person from the `memberUid` of all their groups, deletes the LDAP
entry, removes their Slurm associations (backing them up) and decides what happens to the
home. By default it **keeps it**: deleting somebody's data is irreversible.

And at the end it **verifies that the identity is gone**, which is the answer to the problem
that forced deleting by hand on two hosts:

```
[!] Sigue existiendo una cuenta LOCAL de otro-usuario en este host. Los cambios en LDAP
    no se ven en ese host porque nsswitch resuelve 'files' antes que 'sss'.
    Para limpiarla:
        ssh root@<host> "userdel otro-usuario"
```

---

## 3. Group commands

### `group-create` — create a group with the standard flow

```bash
venv/bin/python kutral_mgr.py group-create labprueba --gid 9100 --members otro-usuario,un-usuario
venv/bin/python kutral_mgr.py group-create labprueba --no-lab
```

It performs the **four steps** of the cluster's flow:

1. **LDAP**, with the members from the start (`memberUid` at creation time, not afterwards)
2. **SSSD**: refreshes the group cache
3. **BeeGFS**: `/mnt/beegfs/labs/<group>` with setgid **2770** (new files inherit the
   laboratory's group)
4. **Slurm**: creates the account and associates every member

If a member does not exist, it **does not create the group half-way**: it warns and touches
nothing.

**Check from the outside:**

```bash
ldapsearch -x -LLL -H ldap://192.0.2.154 -b "ou=Group,<SUFIJO_DEL_DIRECTORIO>" "(cn=labprueba)"
ls -ld /mnt/beegfs/labs/labprueba        # it has to show 2770
sacctmgr show account labprueba
sacctmgr show assoc account=labprueba
```

### `group-show` — inspect a group

```bash
venv/bin/python kutral_mgr.py group-show lab-uno
```

It shows the gid, the members, whether the folder exists and whether the Slurm account is
there.

### `group-add-member` / `group-remove-member`

```bash
venv/bin/python kutral_mgr.py group-add-member labprueba otro-usuario un-usuario
venv/bin/python kutral_mgr.py group-remove-member labprueba otro-usuario
```

`group-add-member` also associates in Slurm, besides LDAP. `group-remove-member` **skips and
reports** whoever has that group as their primary one, and does not touch Slurm unless you
use `--drop-slurm` (removing it can affect jobs in flight).

### `group-delete` — delete a group

```bash
venv/bin/python kutral_mgr.py group-delete labprueba
venv/bin/python kutral_mgr.py group-delete labprueba --force --remove-lab
```

It **refuses** when the group has members, and **says who is affected**. It also refuses
when it is somebody's primary group, even with no members in `memberUid`.

`--force` skips the refusals. The laboratory folder is **kept** unless `--remove-lab`,
because the members' data may be inside it.

---

## 4. Utility

```bash
venv/bin/python kutral_mgr.py gen-password            # 8 characters: the cluster's length
venv/bin/python kutral_mgr.py gen-password --length 12  # another length, if it ever changes
```

---

## The expiry policy

`shadowExpire` is **days since 1 January 1970**, so `20819` is `2027-01-01` (57 years × 365
+ 14 leap days). The tool translates it, but it is worth knowing when you look at the
directory by hand.

What `--expires` accepts:

| You write | Result |
|---|---|
| *(nothing)* | whatever `cluster.expire_default` says; with `"nunca"`, no expiry date |
| `nunca` | no expiry date (marks `-1`, like the active accounts) |
| `2028-12-31` | that exact date |
| `fin-de-anio` | the next time `cluster.year_end` (`01-01`) comes around |
| `1a` / `2a` | one or two years |
| `18m` | eighteen months |
| `90d` | ninety days |

Durations are added from today. And for dates the same rule holds as for everything else:
**the default is no expiry date**, so nobody has to reschedule users because a policy
expires them all in January.

## Mail

Five templates: **creation** (with credentials and the tutorial attached), **modification**
(with the list of changes), **password reset** (with the temporary password), **deactivation**
and **reactivation** (with the temporary password and, when it applies, the expiry date).

The templates come in both languages and go out in the **language of the run**, the same as
the console: with `--idioma es` the person receives the mail in Spanish. The only thing that
does not change with the language is the data —username, password, paths, dates— which is
substituted inside either version.

The policy is decided in `cluster.send_mail`:

| Value | What happens |
|---|---|
| `ask` | asks before sending (when there is a terminal); in a script it sends nothing |
| `always` | always sends |
| `never` | never sends |

It can be forced with `--enviar-correo` or `--no-enviar-correo`. The transport is configured
in `smtp.transport`: `msmtp` (what the cluster uses), `smtp` (a relay) or `file` (writes the
mails as `.eml`, to review them without sending them).

A mail that does not go out **does not bring the operation down**: it warns and moves on.

## Recipes

**Create a student**

```bash
venv/bin/python kutral_mgr.py create-user \
  --full-name "Tercera Usuaria" --username tercer-usuario --group lab-dos \
  --mail tercer.usuario@ejemplo.cl --employee-type student --institute UOH \
  --expires fin-de-anio
# copy the password it prints, and check:
getent passwd tercer-usuario && ssh tercer-usuario@198.51.100.104
```

**End of semester: suspend a whole course**

```bash
for u in tercer-usuario un-usuario otro-usuario; do
  venv/bin/python kutral_mgr.py --simulate deactivate "$u" --reason "fin de semestre"
done
# if the simulation looks right, repeat without --simulate
```

**Change of laboratory**

```bash
venv/bin/python kutral_mgr.py change-group tercer-usuario lab-dos --keep-old
```

**Reactivate with an end-of-year expiry date**

```bash
venv/bin/python kutral_mgr.py reactivate tercer-usuario --expires fin-de-anio --enviar-correo
```

## When something fails

| Message | What it means | What to do |
|---|---|---|
| `El grupo 'X' no existe bajo ou=Group` | the group is not where it is looked for | if it is a group outside `ou=Group` (like `cn=lab-diez`), it is not found by name |
| `Ya existe un grupo llamado 'X' que difiere sólo en mayúsculas` | `cn` does not distinguish case in LDAP | use the existing name, or pick another one |
| `Este comando necesita sacctmgr y no está disponible en este host` | you are on a node without Slurm | run it from the management node |
| `No se pudo refrescar la caché de identidad` | `sss_cache` failed (no root?) | the LDAP change is done; the cache will refresh by itself, more slowly |
| `Tiene cuenta LOCAL en este host` | there is a copy in `/etc/passwd` | `ssh root@<host> "userdel <user>"` on that host |
| `No se pudo asignar dueño a …` | `chown` failed on BeeGFS | check that you are running as root and that BeeGFS is mounted |
| `Por seguridad no se toca 'X'` | the path is outside the configured directories | it is a guard: check `paths.beegfs_home` and `paths.beegfs_labs` |

The messages are printed in the language of the run: the ones above are the Spanish text as
it appears with `es`.

## Frequently asked questions

**Why does `gecos` come out without accents?**
Because this directory defines `gecos` with **ASCII** syntax: an accented name makes the
`add` fail with `LDAPInvalidAttributeSyntaxResult` and **the account is not created** (it
happened on 2026-10-20). The real name, accents included, goes in `cn`, `displayName` and
`sn`, which do accept UTF-8. `gecos` is what `ls -l` shows, and nothing more.

**Why does `sn` hold the surnames and not the full name?**
Because `sn` is the surname in the LDAP schema. The inherited script wrote the full name
there, and that is why 16 accounts in the directory are like that. New ones are created
properly; fixing the old ones is a separate migration.

**Why is the new uid the maximum + 1 and not the first free gap?**
Because a freed uid may still own orphan files on BeeGFS. Reassigning it would hand them
over to somebody else.

**Why does creation not create local users on the hosts?**
Because SSSD resolves directory accounts with no local copy, and those copies were exactly
what made an LDAP change invisible.

**Can I run it from my laptop?**
Only the rehearsal mode (`--config config.lab.yaml`). Against the real cluster it needs
`sacctmgr`, BeeGFS and LDAP access: it is run from the management node.

**What if I make a mistake?**
Every operation writes a **rollback LDIF** in `/root/kutral-backups/` before touching the
entry, and the Slurm associations are backed up before being removed. To revert a
modification:

```bash
ldapmodify -x -H ldap://192.0.2.154 -D "<CUENTA_ADMINISTRADORA>,<SUFIJO_DEL_DIRECTORIO>" -W \
  -f /root/kutral-backups/<file>.ldif
```
