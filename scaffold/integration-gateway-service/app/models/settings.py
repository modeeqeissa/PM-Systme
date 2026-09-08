import datetime as dt
import uuid

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntegrationSetting(Base):
    """integration_settings — admin-editable key/value overrides (migration
    0004). Currently one key, `log_retention_days`; an absent row means "use
    the env-var default" (app.config). Per-service settings table, consistent
    with the database-per-service model.
    """

    __tablename__ = "integration_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # logical FK -> identity_db.users.id (the admin who last changed this)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
