# Decisions

Why the Control Center is the way it is. This is not a user manual (that is
[MANUAL_USO.md](MANUAL_USO.md)) nor a logbook: it is the record of the decisions
that show up in the code and do not explain themselves.

---

## About this published edition

This is the **sanitised edition**, the same copy for the organisation and for the
portfolio. The private repository keeps the real edition, with the cluster configuration
and the internal documents.

**What was replaced, and why**

| What | Why | Replacement value |
|---|---|---|
| Addresses of the directory, the access node and the management server | they are the internal network | RFC 5737 documentation addresses (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`), which exist nowhere and are still valid IPs |
| Directory suffix and administrator account | they identify the installation | the `<SUFIJO_DEL_DIRECTORIO>` and `<CUENTA_ADMINISTRADORA>` placeholders |
| Internal hosts | they identify the machine | fictitious names (`nodo-nextcloud`, `host-ldap`, `host-gestion`) |
| Institution domain and mail | they identify the service | `ejemplo.cl` |
| People's names (username, full name, mail) | they are personal data | `un-usuario`, `otro-usuario`, `tercer-usuario`, … |
| Laboratory names | they identify research groups | `lab-uno`, `lab-dos`, `lab-tres`, … |
| The production configuration | it carries all of the above together | it becomes `config.example.yaml`: the template that is copied to `config.yaml` |

**Why the addresses are not `<...>` placeholders in the code.** The rehearsal mode has a
guard: when the environment is not `prod` and the target falls inside the internal
network, it aborts before connecting. That guard compares real IPs. With a placeholder in
their place, the guard and its test would stop verifying anything —and silently, which is
the worst way to break a test—. The RFC 5737 addresses keep the guard working and point at
no real network.

**Why a single initial commit.** The history of the working repository has names and mail
addresses inside it; rewriting it leaves traces. This copy is born clean, with one commit
on the already sanitised version.

**What is not published.** The infrastructure runbook, the project logbook and the list of
open items: they describe the real installation, with its hosts and its gaps. The script
that builds this edition is not published either, because it holds the real values it
replaces. And of `scripts/` only the **Nextcloud hook** goes in: the three backup
scripts —the directory one, the configuration and certificates one, and their `crontab`—
describe how the infrastructure is put together, where it stores, how long it keeps and
which of those copies failed and when. That stays in the private repository.

## Where it comes from

The control center **continues the cluster administration work that already existed**: the
seven shell and Perl tools that did creations, deletions and changes live in the private
repository `Kutral_config` and were not copied here. What was added in this repository is
the Python program, the ports-and-adapters design, the rehearsal mode and the test suite.
The Slurm commands keep on purpose the shape those scripts already used: nothing that
worked was changed.

---

## Design decisions

### The domain never touches the network

No user or group operation calls `subprocess`, `os.chown` or the network: it asks for
ports, and every port has two implementations (`modules/core/` for the real thing,
`modules/testing/` for the doubles). That is what makes it possible to test 100% of the
decision logic —including deleting an account— with no cluster, no VPN and no risk. The
rehearsal mode uses exactly the same domain modules.

### The rehearsal mode is first class

`config.lab.yaml` brings up an in-memory LDAP directory, a sandbox on disk, a dictionary
Slurm and a mail service that writes `.eml` files. State survives between commands (an
account can be created and then consulted), and `--simulate` against the real configuration
walks the whole flow without writing anything. The suite needs no network.

### The administrator password never touches the disk

It is read from a session environment variable or asked for on the keyboard. The tool asks
for it, uses it and forgets it; the configuration file never carries it in any format. Mail
carries no passwords either: a temporary password is printed once, for whoever hands it over
in person.

### The network guard

When `environment` is not `prod` and the target falls inside the internal network, the tool
**aborts before connecting**. It was born from a rehearsal that came close to writing into
the real directory, and it is the most important test in the suite.

### Explicit expiry dates

With no date, an account becomes permanent and is marked with an explicit `-1` (like the
historical active accounts in the directory), instead of leaving the attribute absent:
"no attribute" and "no expiry date" have to be distinguishable. `--expires fin-de-anio`
points at `01-01`, that is, the account survives the turn of the year. `shadowExpire: 0` is
read as active, and there is a test that pins it down because it is counterintuitive.

### What the tool does not do, on purpose

- **It does not create local users** on any host: SSSD resolves the directory with no local
  copy, and creating copies was the origin of the problem this came to solve.
- **It does not rename groups or change their gid**: changing the `cn` forces moving the
  laboratory folder, the Slurm account and the `departmentNumber` of every member. It is a
  new creation plus a move, and it is done as such.
- **It does not reassign the owner of existing files** when somebody changes laboratory: old
  files keep the previous gid.
- **It does not manage replication**: the directory has a single master.
- **It does not delete the home by default**: it is archived or kept, and deleting it has to
  be asked for.

### Backups: history and two destinations

A backup that always writes into the same folder is a mirror, not a history: if the source
gets corrupted, the next copy overwrites what was good. Copies carry a date, with retention,
and they are verified (that they do not come out empty and that the permissions stay closed,
because a private key travels among the certificates). The directory backup writes to two
destinations: one survives the loss of the shared storage, the other the loss of the server.

### The synthetic directory pins down shapes, not people

The test `seed` reproduces the ranges, the odd cases and the inconsistencies of the real
directory —entries with no `givenName`, `sn` holding the full name, a group hanging off the
root instead of `ou=Group`, values with accents that force base64 in LDIF— but **with
invented names**: it is not updated every time the roll changes, because what it pins down
are the shapes.

### Language

The language of the run is selectable (`--lang` / `--idioma`, `KUTRAL_LANG` or the locale)
and **everything comes out in it**: the console, the audit log and the mails people receive.
That is why the texts live in a single catalog (`modules/common/messages.py`), with both
versions of every message —including the mail templates, under the `mail.*` keys—: a
half-translated entry would show up as a sentence in the wrong language, and there is a test
that prevents it (`test_i18n.py` for the catalog, `test_mailer.py` for the mails).

The code, the comments and the names are in English, and so are the explanatory
documents of this edition: in the private repository they live in Spanish too,
because that is the language the cluster is operated in day to day.
