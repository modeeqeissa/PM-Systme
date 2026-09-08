"""Argon2id password hashing + policy checks (FR-IAM-07, docs Section 9.3.1).

Policy has four parts, all ICT-configurable via env (see app.config):
  * minimum length + per-rule complexity toggles  -> policy_errors()
  * no reuse of the last N passwords               -> is_reused()
  * expiry after a configurable age               -> is_expired()
"""
import datetime as dt
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
    """Length + complexity violations; empty list means the password passes.
    Each complexity rule is individually toggleable (IAM_PASSWORD_REQUIRE_*)."""
    errors: list[str] = []
    if len(raw) < config.PASSWORD_MIN_LENGTH:
        errors.append(f"must be at least {config.PASSWORD_MIN_LENGTH} characters")
    if config.PASSWORD_REQUIRE_LOWER and not re.search(r"[a-z]", raw):
        errors.append("must contain a lowercase letter")
    if config.PASSWORD_REQUIRE_UPPER and not re.search(r"[A-Z]", raw):
        errors.append("must contain an uppercase letter")
    if config.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", raw):
        errors.append("must contain a digit")
    if config.PASSWORD_REQUIRE_SYMBOL and not re.search(r"[^A-Za-z0-9]", raw):
        errors.append("must contain a symbol")
    return errors


def is_reused(raw: str, recent_hashes: list[str]) -> bool:
    """True if `raw` matches any hash in `recent_hashes` (the current password
    plus the last N-1 from password_history). No-op when history is disabled
    (the caller passes an empty list)."""
    return any(verify_password(raw, h) for h in recent_hashes)


def is_expired(password_changed_at: dt.datetime | None) -> bool:
    """True once the password is older than IAM_PASSWORD_MAX_AGE_DAYS.
    Always False when max age is 0 (expiry disabled) or the timestamp is unknown."""
    if config.PASSWORD_MAX_AGE_DAYS <= 0 or password_changed_at is None:
        return False
    now = dt.datetime.now(dt.timezone.utc)
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=dt.timezone.utc)
    return (now - password_changed_at) > dt.timedelta(days=config.PASSWORD_MAX_AGE_DAYS)
