"""Temporary password generation and hashing compatible with the directory.

Scheme verified in production: `userPassword: {CRYPT}$6$<salt>$<hash>`, produced by
create_users.pl with crypt SHA-512 and a 16-character salt. That format is kept so as
not to change anything while the rest settles.

About the SHA-512 crypt implementation
--------------------------------------
The standard library's `crypt` module exists up to Python 3.12 and was **removed in
3.13**. The cluster runs 3.9 and has it, but the development notebook probably does
not. That is why there is a pure-Python implementation, validated against Ulrich
Drepper's reference vectors:

    sha512_crypt("Hello world!", salt="saltstring")
      == "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjn"
         "QJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1"

This also leaves the project ready for the day the cluster moves to a newer Python.
"""

from __future__ import annotations

import hashlib
import secrets
import string
from typing import Optional

from .errors import KutralError
from .i18n import t

try:  # the C module is preferred when it exists: it is faster
    import crypt as _crypt
except ImportError:  # pragma: no cover - Python >= 3.13
    _crypt = None  # type: ignore[assignment]

# Password alphabet. Symbols are deliberately few: `-_.@+=`. Left out are the ones a
# shell interprets if someone pastes the password into a command line or a script
# (`$`, `&`, `!`, `#`, `*`), the parentheses —which force quoting and confuse people
# when the password is dictated or copied— and `^`, which the inherited generator
# already excluded.
SYMBOLS = "-_.@+="
DEFAULT_ALPHABET = string.ascii_letters + string.digits + SYMBOLS
LOWER = string.ascii_lowercase
UPPER = string.ascii_uppercase
DIGITS = string.digits

SALT_ALPHABET = string.ascii_letters + string.digits + "./"
B64_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# Output permutation of SHA-512 crypt (Drepper's table). Each triple
# (high, mid, low) is emitted in base64 backwards, 4 characters per triple.
_SHA512_PERMUTATION = (
    (0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4),
    (47, 5, 26), (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51),
    (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13), (56, 14, 35),
    (15, 36, 57), (37, 58, 16), (59, 17, 38), (18, 39, 60), (40, 61, 19),
    (62, 20, 41),
)


def _b64_from_24bit(high: int, mid: int, low: int, count: int) -> str:
    """Emit `count` characters of the triple, from the least significant bit up."""
    value = (high << 16) | (mid << 8) | low
    return "".join(B64_ALPHABET[(value >> (6 * i)) & 0x3F] for i in range(count))


def sha512_crypt(password: str, salt: str, rounds: int = 5000) -> str:
    """Pure-Python implementation of SHA-512 crypt, `$6$` format.

    It reproduces Drepper/glibc's algorithm exactly, including the bit mask over the
    password length and the final base64 permutation.
    """
    password_bytes = password.encode("utf-8")
    # The spec (Drepper) and glibc cap the salt at SALT_LEN_MAX = 16 characters, and
    # production always uses exactly 16 (create_users.pl). It is truncated to
    # reproduce that behaviour; see the vector validation in the tests.
    salt = salt[:16]
    salt_bytes = salt.encode("utf-8")
    key_length = len(password_bytes)

    # Digest B: password + salt + password
    digest_b = hashlib.sha512(password_bytes + salt_bytes + password_bytes).digest()

    # Digest A
    context = hashlib.sha512()
    context.update(password_bytes)
    context.update(salt_bytes)
    context.update(digest_b * (key_length // 64))
    context.update(digest_b[: key_length % 64])
    remaining = key_length
    while remaining:
        context.update(digest_b if remaining & 1 else password_bytes)
        remaining >>= 1
    digest_a = context.digest()

    # Sequence P: the password repeated up to key_length bytes
    p_seed = hashlib.sha512(password_bytes * key_length).digest()
    p_bytes = p_seed * (key_length // 64) + p_seed[: key_length % 64]

    # Sequence S: the salt repeated 16 + first byte of A times
    s_seed = hashlib.sha512(salt_bytes * (16 + digest_a[0])).digest()
    salt_length = len(salt_bytes)
    s_bytes = s_seed * (salt_length // 64) + s_seed[: salt_length % 64]

    # Rounds
    result = digest_a
    for index in range(rounds):
        context = hashlib.sha512()
        context.update(p_bytes if index & 1 else result)
        if index % 3:
            context.update(s_bytes)
        if index % 7:
            context.update(p_bytes)
        context.update(result if index & 1 else p_bytes)
        result = context.digest()

    # Final encoding
    encoded = "".join(_b64_from_24bit(result[i], result[j], result[k], 4)
                      for i, j, k in _SHA512_PERMUTATION)
    encoded += _b64_from_24bit(0, 0, result[63], 2)

    prefix = "$6$"
    if rounds != 5000:
        prefix += "rounds={}$".format(rounds)
    return "{}{}${}".format(prefix, salt, encoded)


def generate_secure_password(length: int = 12, alphabet: str = DEFAULT_ALPHABET) -> str:
    """Generate a temporary password with `secrets`.

    It guarantees at least one lowercase letter, one uppercase letter, one digit and
    one symbol, and the symbol comes from `SYMBOLS`: the ones that break neither the
    shell nor LDIF. It is stricter than the inherited `openssl rand -base64 6`, which
    could come out with no digits and no lowercase letters and broke the complexity
    policies.

    Args:
        length: desired length. Minimum 8.
        alphabet: character vocabulary.
    """
    if length < 8:
        length = 8
    if not (set(LOWER) <= set(alphabet) and set(UPPER) <= set(alphabet)
            and set(DIGITS) <= set(alphabet) and set(SYMBOLS) <= set(alphabet)):
        raise KutralError(t("msg.password.alphabet"))
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c in LOWER for c in password)
                and any(c in UPPER for c in password)
                and any(c in DIGITS for c in password)
                and any(c in SYMBOLS for c in password)):
            return password


def make_salt(length: int = 16) -> str:
    """Random salt in the crypt alphabet (it includes '.' and '/')."""
    return "".join(secrets.choice(SALT_ALPHABET) for _ in range(length))


def hash_password(password: str, scheme: str = "{CRYPT}", salt: Optional[str] = None) -> str:
    """Return the value as it is stored in `userPassword`.

    With scheme "{CRYPT}" it produces `{CRYPT}$6$<salt>$<hash>`: the same format the
    directory already holds. It uses the `crypt` module when available and, if not, the
    pure-Python implementation.
    """
    if scheme != "{CRYPT}":
        # Careful: a literal "{CRYPT}" inside a .format() would be a field, not text.
        raise KutralError(t("msg.password.scheme", scheme=scheme))
    salt = salt or make_salt(16)
    if _crypt is not None:
        digest = _crypt.crypt(password, "$6${}$".format(salt))
        if not digest:
            raise KutralError(t("msg.password.crypt_failed"))
    else:
        digest = sha512_crypt(password, salt)
    return "{CRYPT}" + digest


def mask(value: Optional[str]) -> str:
    """Masked representation, to show without leaking the value."""
    return "*" * len(value) if value else t("msg.render.empty")
