import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # logical FK -> hr_db.officers.id
    facilitator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    meeting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)


class Concern(Base):
    __tablename__ = "concerns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_progress','resolved')", name="ck_concerns_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id")
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open"
    )


class FollowUpAction(Base):
    __tablename__ = "follow_up_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','overdue','completed')",
            name="ck_follow_up_actions_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    concern_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concerns.id"), nullable=False
    )
    # logical FK -> hr_db.officers.id
    assigned_to: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
