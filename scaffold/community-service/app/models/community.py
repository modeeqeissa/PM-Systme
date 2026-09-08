import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Community(Base):
    """communities — a named neighbourhood/group per station (docs §9.3.4)."""

    __tablename__ = "communities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Organization(Base):
    """organizations — partner orgs, optionally tied to a community (docs §9.3.4)."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="SET NULL")
    )
    contact_name: Mapped[str | None] = mapped_column(String(150))
    contact_phone: Mapped[str | None] = mapped_column(String(30))


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # nullable FK -> communities.id (migration 0004) — the specific community
    # this meeting was held with, where applicable (docs §9.3.4).
    community_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="SET NULL")
    )
    # logical FK -> hr_db.officers.id
    facilitator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    meeting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    attendee_summary: Mapped[str | None] = mapped_column(Text)


class MeetingMinutes(Base):
    """meeting_minutes — one formal minutes record per meeting (docs §9.3.4)."""

    __tablename__ = "meeting_minutes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # logical FK -> hr_db.officers.id
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class Decision(Base):
    """decisions — a formal resolution made at a meeting, with its own
    pending/implemented/abandoned lifecycle (docs §9.3.4)."""

    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','implemented','abandoned')", name="ck_decisions_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )


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
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raised_by: Mapped[str | None] = mapped_column(String(150))
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
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # logical FK -> hr_db.officers.id
    assigned_to: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
