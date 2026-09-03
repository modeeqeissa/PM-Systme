import datetime as dt
import uuid

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

CUSTODY_ACTIONS = (
    "collected",
    "transferred",
    "analyzed",
    "stored",
    "submitted_court",
    "disposed",
)
# Actions that move custody to another officer and so require the receiving
# officer's acknowledgement (FR-EVID-04).
ACK_REQUIRED_ACTIONS = ("transferred", "submitted_court")


class CustodyEvent(Base):
    """custody_events — docs Section 9.3.3. APPEND-ONLY.

    The database REVOKEs UPDATE/DELETE on this table from the application role
    and BEFORE UPDATE/DELETE triggers reject the operations outright (migration
    0001). Never write an UPDATE or DELETE against this model.
    """

    __tablename__ = "custody_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('collected','transferred','analyzed','stored',"
            "'submitted_court','disposed')",
            name="ck_custody_events_action",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    from_officer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_officer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # SHA-256 hash of the receiving officer's signature/PIN (never the raw value).
    acknowledgement_signature: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
