"""Request/response models for /iam-settings (FR-IAM-07)."""
from pydantic import BaseModel, ConfigDict


class IamSettingsPatch(BaseModel):
    """Partial update of the password policy. Omitted keys are left unchanged;
    a key set back to its env default simply removes the override."""

    model_config = ConfigDict(extra="forbid")

    password_min_length: int | None = None
    password_require_lower: bool | None = None
    password_require_upper: bool | None = None
    password_require_digit: bool | None = None
    password_require_symbol: bool | None = None
    password_history_count: int | None = None
    password_max_age_days: int | None = None


class IamSettingsOut(BaseModel):
    """Effective policy: each key's live value, plus which keys are currently
    overridden by an `iam_settings` row (vs. still on the env default)."""

    values: dict[str, int | bool]
    overridden: list[str]
