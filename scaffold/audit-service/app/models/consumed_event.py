import datetime as dt
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConsumedEvent(Base):
    """Service-local idempotency ledger (CLAUDE.md rule 5).

    One row per Kafka event_id already turned into an audit entry, so at-least-once
    redelivery never double-writes history (SRS §9.4 "idempotent consumers").
    """

    __tablename__ = "consumed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
