"""DB-backed password-policy settings (FR-IAM-07).

The `IAM_PASSWORD_*` env vars are now the **seed / default only** — an admin can
override any of them at runtime through `PATCH /iam-settings`, which writes an
`iam_settings` row. This module holds the small in-process cache the (sync,
session-less) policy checks in `app.security.passwords` read from; it is loaded
on startup and re-loaded after every settings write, exactly like the JWKS
cache.

Keys and their coercion:
    password_min_length      int  >= 1
    password_require_lower    bool
    password_require_upper    bool
    password_require_digit    bool
    password_require_symbol   bool
    password_history_count    int  >= 0   (0 disables the reuse check)
    password_max_age_days     int  >= 0   (0 disables expiry)
"""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.models import IamSetting


def _to_bool(raw) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# key -> (coerce, validate, default-from-env)
_SPEC = {
    "password_min_length": (int, lambda v: v >= 1, lambda: config.PASSWORD_MIN_LENGTH),
    "password_require_lower": (_to_bool, lambda v: True, lambda: config.PASSWORD_REQUIRE_LOWER),
    "password_require_upper": (_to_bool, lambda v: True, lambda: config.PASSWORD_REQUIRE_UPPER),
    "password_require_digit": (_to_bool, lambda v: True, lambda: config.PASSWORD_REQUIRE_DIGIT),
    "password_require_symbol": (_to_bool, lambda v: True, lambda: config.PASSWORD_REQUIRE_SYMBOL),
    "password_history_count": (int, lambda v: v >= 0, lambda: config.PASSWORD_HISTORY_COUNT),
    "password_max_age_days": (int, lambda v: v >= 0, lambda: config.PASSWORD_MAX_AGE_DAYS),
}

_cache: dict[str, str] = {}


def keys() -> tuple[str, ...]:
    return tuple(_SPEC)


class SettingError(ValueError):
    """Bad key or value in a PATCH body."""


def coerce(key: str, raw) -> str:
    """Validate one incoming value and return its canonical string form for the
    row. Raises SettingError on an unknown key or an invalid value."""
    if key not in _SPEC:
        raise SettingError(f"unknown setting {key!r}")
    to_py, ok, _default = _SPEC[key]
    try:
        py = to_py(raw)
    except (TypeError, ValueError):
        raise SettingError(f"{key}: not a valid {to_py.__name__}")
    if not ok(py):
        raise SettingError(f"{key}: value out of range")
    return "true" if py is True else "false" if py is False else str(py)


def get(key: str):
    """Effective (typed) value: the cached override if present, else the env default."""
    to_py, _ok, default = _SPEC[key]
    if key in _cache:
        return to_py(_cache[key])
    return default()


def effective() -> dict:
    return {k: get(k) for k in _SPEC}


def overridden() -> list[str]:
    return sorted(k for k in _SPEC if k in _cache)


async def refresh(session: AsyncSession) -> None:
    rows = (await session.scalars(select(IamSetting))).all()
    _cache.clear()
    _cache.update({r.key: r.value for r in rows if r.key in _SPEC})


def _load_from_rows(rows: Iterable[IamSetting]) -> None:
    """Test/seed helper — populate the cache without a DB round-trip."""
    _cache.clear()
    _cache.update({r.key: r.value for r in rows if r.key in _SPEC})
