"""Request/response models for /integration-settings (Phase 5).

`INTEGRATION_GATEWAY_LOG_RETENTION_DAYS` is the seed/default; a PATCH here
writes an `integration_settings` row that overrides it at runtime.
"""
from pydantic import BaseModel, ConfigDict


class IntegrationSettingsPatch(BaseModel):
    """Partial update. Omitted keys are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    log_retention_days: int | None = None


class IntegrationSettingsOut(BaseModel):
    """Effective settings: each key's live value, plus which keys are currently
    overridden by an `integration_settings` row (vs. still on the env default)."""

    values: dict[str, int]
    overridden: list[str]
