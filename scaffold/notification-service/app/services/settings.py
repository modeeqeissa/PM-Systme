"""DB-backed admin settings (notification_settings, Phase 5).

`NOTIFICATION_RETENTION_DAYS` is the seed/default; `PATCH
/notification-settings` writes a row that overrides it at runtime. The
retention worker reads the effective value through `get()` (cache reloaded on
startup and after every write).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.models import NotificationSetting

# key -> (coerce, validate, default-from-env)
_SPEC = {
    "retention_days": (int, lambda v: v >= 1, config.retention_days),
}

_cache: dict[str, str] = {}


class SettingError(ValueError):
    """Bad key or value in a PATCH body."""


def keys() -> tuple[str, ...]:
    return tuple(_SPEC)


def coerce(key: str, raw) -> str:
    if key not in _SPEC:
        raise SettingError(f"unknown setting {key!r}")
    to_py, ok, _default = _SPEC[key]
    try:
        py = to_py(raw)
    except (TypeError, ValueError):
        raise SettingError(f"{key}: not a valid {to_py.__name__}")
    if not ok(py):
        raise SettingError(f"{key}: value out of range")
    return str(py)


def get(key: str):
    to_py, _ok, default = _SPEC[key]
    if key in _cache:
        return to_py(_cache[key])
    return default()


def effective() -> dict:
    return {k: get(k) for k in _SPEC}


def overridden() -> list[str]:
    return sorted(k for k in _SPEC if k in _cache)


async def refresh(session: AsyncSession) -> None:
    rows = (await session.scalars(select(NotificationSetting))).all()
    _cache.clear()
    _cache.update({r.key: r.value for r in rows if r.key in _SPEC})
