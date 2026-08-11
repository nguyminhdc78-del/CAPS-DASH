"""Password hashing with argon2id.

argon2-cffi directly, not passlib: passlib is unmaintained and its bcrypt
backend broke against bcrypt 4.x. One less abandoned layer between this system
and the only thing standing between an attacker and every account.

argon2id is deliberately slow and memory-hard, so an offline crack of a stolen
database costs years rather than hours. That is the entire point - a fast hash
here is a bug, not an optimisation.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Verified against when the username does not exist, so a login attempt costs
# the same either way. Without it, "no such user" returns measurably faster
# than "wrong password", and that timing difference enumerates accounts.
DUMMY_HASH = _hasher.hash("a-fixed-throwaway-string-never-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password. Never raises - a malformed stored hash is just a failure."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def consume_dummy_verification(password: str) -> None:
    """Burn the same CPU a real verification would, and discard the result."""
    verify_password(DUMMY_HASH, password)


def needs_rehash(password_hash: str) -> bool:
    """Whether this hash predates the current parameters.

    Lets the cost be raised later without locking anyone out: on the next
    successful login the stored hash is quietly upgraded.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
