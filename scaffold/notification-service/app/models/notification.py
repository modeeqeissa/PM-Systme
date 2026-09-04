import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)


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
