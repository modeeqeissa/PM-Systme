import datetime as dt
import uuid

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import CHAR, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

AUDIT_ACTIONS = ("create", "read", "update", "delete", "export")


class AuditLog(Base):
    """audit_logs — docs Section 9.3.10. APPEND-ONLY, hash-chained.

    The database REVOKEs UPDATE/DELETE on this table from the application role
    and BEFORE UPDATE/DELETE triggers reject the operations outright (migration
    0001). Never write an UPDATE or DELETE against this model.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create','read','update','delete','export')",
            name="ck_audit_logs_action",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    service_name: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    prev_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    record_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
