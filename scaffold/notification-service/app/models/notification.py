import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('email','sms','push','in_app')", name="ck_notifications_channel"
        ),
        CheckConstraint(
            "status IN ('queued','sent','delivered','failed')",
            name="ck_notifications_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # logical FK -> identity_db.users.id
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("notification_templates.code"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="queued"
    )


class OfficerUserMap(Base):
    """officer_id -> user_id lookup (service-local, not SRS-tracked — same
    category as dashboard-service's dash_case dimension).

    Every domain event that should trigger a notification for an officer
    (TransferStatusChanged, LeaveStatusChanged, OfficerCertificationStatus
    Changed, FollowUpActionStatusChanged) carries only officer_id (hr_db.
    officers.id), but notifications.recipient_user_id must be identity_db.
    users.id. hr-service's OfficerCreated is the only event that carries
    both, so this table is fed from it — CLAUDE.md rule 1 (no cross-service
    DB access) means notification-service cannot just look the mapping up in
    hr_db directly.
    """

    __tablename__ = "officer_user_map"

    officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # the officer's direct supervisor (another officer), for FR-COMM-04
    # escalation — fed by hr.officer_created / hr.officer_supervisor_changed.
    supervisor_officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class NotificationPreference(Base):
    """Per-user opt-out per channel (FR-NOTIF-02). Absence of a row means the
    channel is enabled (default)."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", name="uq_notification_preferences_user_channel"),
        CheckConstraint(
            "channel IN ('email','sms','push','in_app')",
            name="ck_notification_preferences_channel",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ConsumedEvent(Base):
    """Idempotency ledger — one row per Kafka event_id already applied (SRS §9.4)."""

    __tablename__ = "consumed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
