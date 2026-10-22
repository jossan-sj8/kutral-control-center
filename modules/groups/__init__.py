"""POSIX group domain.

The standard flow for creating a group on this cluster is **four** steps, in this
order, and none of them is optional:

    1. LDAP: the posixGroup **with its members from the start** (`memberUid`).
       Groups behave better that way than by adding members afterwards; it is what
       `add_users.sh` itself does with its `ldap_add_group` + `ldapmodify`.
    2. SSSD: cache refresh so the system recognises the group right away.
    3. BeeGFS: `/mnt/beegfs/labs/<group>` owned by the group, **setgid 2770**, so
       new files inherit the group and the lab is collaborative.
    4. Slurm: `sacctmgr add account <group>` and the association of every member
       (`create user name=... account=<group>`), because on this cluster the Slurm
       account **is** the group.

All four live here, in one place, instead of being spread over `add_users.sh`,
`add_group.sh` and two hosts.
"""
