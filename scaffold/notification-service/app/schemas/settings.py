"""Request/response models for /notification-settings (Phase 5).

`NOTIFICATION_RETENTION_DAYS` is the seed/default; a PATCH here writes a
`notification_settings` row that overrides it at runtime.
"""
from pydantic import BaseModel, ConfigDict


class NotificationSettingsPatch(BaseModel):
    """Partial update. Omitted keys are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    retention_days: int | None = None


class NotificationSettingsOut(BaseModel):
    """Effective settings: each key's live value, plus which keys are currently
    overridden by a `notification_settings` row (vs. still on the env default)."""

    values: dict[str, int]
    overridden: list[str]
