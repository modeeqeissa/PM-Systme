import datetime as dt
import uuid

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IamSetting(Base):
    """iam_settings — admin-editable key/value overrides for the password
    policy (migration 0011 / FR-IAM-07). An absent key means "use the env-var
    default" (app.config); a present row overrides it at runtime.

    Per-service settings table, not a centralised settings service — consistent
    with the database-per-service model.
    """

    __tablename__ = "iam_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # logical FK -> users.id (the admin who last changed this)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
