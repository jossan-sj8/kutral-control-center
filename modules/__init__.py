"""Kutral Control Center — user and group lifecycle management.

Organised by infrastructure domain:

    common/   prompts, passwords, output formatting, exceptions
    core/     LDAP, Slurm, mail, BeeGFS storage, SSSD, audit
    users/    creation, consultation, modification, deactivation, reactivation, deletion
    groups/   creation, modification and deletion of POSIX groups
    reports/  export and audit cross-checking

Design rule: the domain (users/, groups/) never calls subprocess nor os.chown directly.
It talks to the ports defined in core/ports.py, which have a real implementation and a
fake one. That is what makes it possible to test all of this without being on the
cluster.
"""

__version__ = "2.0.0.dev0"
