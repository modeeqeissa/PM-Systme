import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


def _created_at() -> Mapped[dt.datetime]:
    """Service-local ordering/audit metadata (migration 0003) — NOT a docs
    Section 9.3.6 column. These tables have no domain timestamp of their own
    (unlike assignments.start_date), and "history"/"newest first" listing
    needs one; a gen_random_uuid() PK isn't chronologically sortable."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class Officer(Base):
    __tablename__ = "officers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','on_leave','suspended','retired')",
            name="ck_officers_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    # logical FK -> identity_db.users.id
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False
    )
    badge_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    rank: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id"), nullable=False
    )
    hire_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id"), nullable=False
    )
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date | None] = mapped_column(Date)


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')", name="ck_transfers_status"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    from_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id")
    )
    to_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    # docs Section 9.3.6: set automatically at request time, not client-supplied
    # (unlike created_at, this IS an SRS-tracked domain fact, not bookkeeping).
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # set only on approval (docs Section 9.3.6) — remain NULL on rejection
    effective_date: Mapped[dt.date | None] = mapped_column(Date)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id")
    )
    created_at: Mapped[dt.datetime] = _created_at()


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    previous_rank: Mapped[str] = mapped_column(String(50), nullable=False)
    new_rank: Mapped[str] = mapped_column(String(50), nullable=False)
    # no separate approval workflow (no status column) — supplied at recording
    # time instead (docs Section 9.3.6, both NOT NULL)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    created_at: Mapped[dt.datetime] = _created_at()


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_leave_requests_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    leave_type: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    # set only on approval (docs Section 9.3.6) — remains NULL on rejection
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id")
    )
    created_at: Mapped[dt.datetime] = _created_at()


class DisciplineRecord(Base):
    __tablename__ = "discipline_records"

    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    incident_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(100))
    # drives additional RBAC / audit scrutiny (docs Section 9.3.6)
    confidentiality_level: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="restricted"
    )
    created_at: Mapped[dt.datetime] = _created_at()


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"

    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("officers.id"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _created_at()
