import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import CHAR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ITEM_STATUSES = ("logged", "in_analysis", "in_court", "disposed")


class EvidenceItem(Base):
    """evidence_items — docs Section 9.3.3."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('logged','in_analysis','in_court','disposed')",
            name="ck_evidence_items_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # logical FK -> case_db.cases.id (no cross-service physical FK, CLAUDE.md)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # logical FK -> hr_db.officers.id
    collected_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    collected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    storage_ref: Mapped[str | None] = mapped_column(String(255))
    sha256_hash: Mapped[str | None] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="logged"
    )
