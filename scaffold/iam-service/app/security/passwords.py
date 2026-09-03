"""Argon2id password hashing + policy checks (FR-IAM-07, docs Section 9.3.1)."""
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app import config

_hasher = PasswordHasher()  # argon2id defaults


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, raw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def policy_errors(raw: str) -> list[str]:
    """Return a list of policy violations; empty list means the password passes.

    NOTE: length + complexity only. Password *history* and *expiry* (FR-IAM-07)
    need columns identity_db does not define yet (Section 9.3.1) - flagged for
    an SRS revision before they can be enforced.
    """
    errors: list[str] = []
    if len(raw) < config.PASSWORD_MIN_LENGTH:
        errors.append(f"must be at least {config.PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[a-z]", raw):
        errors.append("must contain a lowercase letter")
    if not re.search(r"[A-Z]", raw):
        errors.append("must contain an uppercase letter")
    if not re.search(r"\d", raw):
        errors.append("must contain a digit")
    if not re.search(r"[^A-Za-z0-9]", raw):
        errors.append("must contain a symbol")
    return errors
