import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Incident(Base):
    """incidents — migration 0001 / docs Section 9.3.2."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    reported_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reported_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Stores the Idempotency-Key header for field-originated writes (FR-CASE-10).
    client_sync_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
