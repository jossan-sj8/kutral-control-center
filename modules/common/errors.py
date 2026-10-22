"""Exceptions of the Kutral Control Center.

An explicit hierarchy is used instead of printing and returning None, so that the CLI
can decide the exit code and so that the tests can assert on the type of error instead
of on printed text.
"""


class KutralError(Exception):
    """Base error. Everything the CLI must report as a controlled error."""


class ConfigError(KutralError):
    """Missing or invalid configuration, or one pointing at a forbidden target."""


class OperationCancelled(KutralError):
    """The operator cancelled from an interactive prompt (q / Ctrl+C)."""


class DirectoryError(KutralError):
    """Failure reading from or writing to the LDAP directory."""


class EntryNotFound(KutralError):
    """The account or group being looked for does not exist in the directory."""


class EntryExists(KutralError):
    """An account or group with that uid/cn/gid already exists."""


class SlurmError(KutralError):
    """Failure talking to Slurm (sacctmgr/squeue)."""


class StorageError(KutralError):
    """Failure operating on shared directories (BeeGFS)."""


class MailError(KutralError):
    """Failure delivering a mail."""


class IdentityError(KutralError):
    """Failure refreshing or resolving identity (SSSD)."""
