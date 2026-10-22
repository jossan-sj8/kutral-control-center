# Kutral Control Center

Command-line tool for the **user and group lifecycle** of the Kutral cluster
(Universidad de O'Higgins): creating, querying, modifying, deactivating,
reactivating and deleting accounts, touching **every** system where an account
lives — LDAP, BeeGFS home, Slurm account, mail and (when needed) Nextcloud.

It replaces a flow of seven shell and Perl scripts spread over several hosts, which
had three underlying problems:

1. **The same person existed in several places that did not talk to each other.**
   Local account by Ansible on two hosts, entry in LDAP, account in Slurm, folder in
   BeeGFS. A change in LDAP was not visible on the hosts, because `nsswitch` resolves
   `files` before `sss`.
2. **Nothing could be tested without touching the cluster.** There were no tests, and
   no way to rehearse a destructive flow.
3. **The rules were baked into the code.** "End of year" was a hardcoded date inside a
   script; passwords travelled on the command line.

## Status

The milestones of the plan are closed, with **236 tests** in the suite. What works today:

| | |
|---|---|
| **Against the real cluster** | every command: the five adapters are real |
| **In rehearsal, without the cluster** | every command: `--config config.lab.yaml` uses an in-memory directory and an on-disk sandbox |
| **Read-only** | `status`, `consult`, `export`, `verify` |
| **Writes** | create, modify, change group, rename, deactivate, reactivate, delete, and the three group commands |

The list of pending work, the infrastructure runbook and the project log live in the
cluster's private repository, with the real data: they are not published. What stays
here is the program and how it is tested.

## Installation

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Three runtime dependencies (`ldap3`, `PyYAML`, `openpyxl`) and none of them needs
compiling. The cluster runs Python 3.9, which is the target version.

## Usage

```bash
# query (read-only)
venv/bin/python kutral_mgr.py status
venv/bin/python kutral_mgr.py consult un-usuario
venv/bin/python kutral_mgr.py export

# create an account
venv/bin/python kutral_mgr.py create-user --full-name "Otro Usuario" \
    --username otro-usuario --group lab-uno --mail otro@ejemplo.cl

# interactive creation: with no flags it asks only for what is missing, and shows a
# summary before writing anything (q or Ctrl+C cancels)
venv/bin/python kutral_mgr.py create-user

# change lab (moves gidNumber, memberUid, departmentNumber and Slurm)
venv/bin/python kutral_mgr.py change-group otro-usuario lab-dos

# suspend and reactivate, expiring at the end of the year
venv/bin/python kutral_mgr.py deactivate otro-usuario --reason "fin de semestre"
venv/bin/python kutral_mgr.py reactivate otro-usuario --expires fin-de-anio
```

Every global flag (`--config`, `--simulate`, `--json`, `--yes`,
`--enviar-correo` / `--no-enviar-correo`, `--sin-cabecera`) works **before or after**
the subcommand.

The full manual — the 21 commands and what to check outside the tool for each of
them — is in [docs/MANUAL_USO.md](docs/MANUAL_USO.md).

## Rehearsal mode: the piece that makes the rest possible

```bash
venv/bin/python kutral_mgr.py --config config.lab.yaml status
venv/bin/python kutral_mgr.py --config config.lab.yaml create-user --yes \
    --full-name "Prueba Test" --username ptest --group lab-uno --mail ptest@ejemplo.cl
venv/bin/python kutral_mgr.py --config config.lab.yaml consult ptest
```

With `config.lab.yaml` the LDAP directory is a synthetic **in-memory** one, storage is
an on-disk sandbox, Slurm is a dictionary and mail is written as `.eml` files. There is
no network, no VPN and nothing to break. State is kept in `sandbox/directory.json`, so
commands can be chained: create an account and then query it.

And `--simulate` against the **production** configuration uses the real adapters
without writing anything: it is the rehearsal before any real operation.

## Architecture

The domain (users, groups) **never** calls `subprocess`, nor `os.chown`, nor the
network. It talks to ports, and every port has two implementations:

```
   kutral_mgr.py  →  cli/commands.py  →  users/, groups/     (the domain)
                                              │
                                      core/ports.py          (the contracts)
                                              │
              ┌───────────────────────────────┴────────────────────────────┐
        real (modules/core/)                                    doubles (modules/testing/)
   ldap_directory.py   real Slurm and LDAP              fake_directory.py   in-memory directory
   slurm_admin.py      sacctmgr                         fake_services.py    Slurm, mail, disk, identity
   identity.py         sss_cache, getent, /etc/passwd
   storage.py          BeeGFS (with a path guard)
   smtp_mailer.py      msmtp, SMTP or .eml files
```

That is what makes it possible to test 100% of the decision logic without a cluster,
and what makes rehearsal mode run on exactly the same domain modules.

## Layout

```
kutral_mgr.py            The CLI: parser, header and output
config.example.yaml       Example configuration (copied to config.yaml)
config.lab.yaml          Rehearsal configuration
modules/
  common/    prompts, errors, validation, passwords, mail policy, formatting
  core/      config, ports, LDAP, states, expiry, Slurm, identity,
             storage, mail, hooks, audit, reports
  users/     creation, consultation, modification, lifecycle, deletion
  groups/    creation, modification, deletion
  cli/       environment wiring and the 20 commands
  testing/   fake directory, service doubles and synthetic seed
tests/       20 test files
docs/        usage manual and decisions
```

## Configuration

Everything lives in `config.example.yaml` (see the comments in the file). What is worth knowing:

| Key | What it does |
|---|---|
| `ldap.server` | the single master of the directory (there is no replication) |
| `ldap.password_env` | session variable the Manager password is read from; there is no password file |
| `cluster.send_mail` | `ask` (asks), `always`, `never` |
| `cluster.expire_default` | what is applied when no date is given: `nunca` (never) by default |
| `cluster.year_end` | what `--expires fin-de-anio` means (`01-01` = survives the new year) |
| `cluster.permanent_marker` | how an account without expiry is marked: explicit `-1` or absent attribute |
| `guard_networks` | networks where rehearsal mode **refuses** to operate |
| `hooks` | external commands (optional, see below) |

The Manager password **is never stored on disk in any format or with any permissions**:
not in the repository, not in `config.yaml`, not in a separate file. It is read from
`KUTRAL_LDAP_PASSWORD` in the session and, if it is not there, the tool asks for it at
the keyboard.

And there is a deliberate network guard: if `environment` is not `prod` and the target
falls inside `192.0.2.0/24`, the tool **aborts before connecting**. That is what stops
a test configuration from writing to the real cluster.

## Tests

```bash
venv/bin/python -m pytest -q
```

236 tests. None of them needs a cluster, a network or a VPN, and they run the same on
Python 3.9, which is what the cluster uses.

## What this tool does NOT do

Deliberate decisions, not oversights:

- **It does not create local users** on any host. SSSD resolves directory accounts
  without a local copy; creating copies was precisely the origin of the problem.
- **It does not rename groups or change their gid.** Changing the `cn` forces moving
  the lab folder, the Slurm account and every member's `departmentNumber`: it is a new
  creation plus a migration.
- **It does not reassign the owner of existing files** when someone changes group. Old
  files keep the previous gid.
- **It does not manage LDAP replication.** There is none configured today.
- **It does not create the Nextcloud mount** for a new lab. It is planned as a separate
  command (`nextcloud-lab`), not implemented yet.

## Scope of this edition

This is the **sanitized edition**: the names of people and labs, the network addresses,
the internal hosts and the domain were replaced by fictitious values (the RFC 5737
documentation addresses and the `ejemplo.cl` domain). The program is the same one that
runs in production; what changes is the data.

What describes the real installation — the runbook, the log and the list of pending
work — stays in the private repository.

The history starts with a single commit: this copy is born clean.

## Credits

Developed for the Kutral cluster of the Universidad de O'Higgins. The Slurm commands
inherit the shapes already used by the cluster's scripts (`add_users.sh`,
`user_mgmt.py`), so as not to change what already worked.

### Where this comes from

This control center **continues the cluster administration work that already existed**:
the seven shell and Perl tools that did these tasks live in the private `Kutral_config`
repository and were **not copied into this repository**. What was added here is the
Python program, the port adapters, rehearsal mode and the test suite. The Slurm
commands deliberately keep the shape those scripts already used, so as not to change
what already worked.
