import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

USER_STATUSES = ("active", "suspended", "deactivated")


class User(Base):
    """users — docs Section 9.3.1."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','suspended','deactivated')", name="ck_users_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    badge_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # TOTP secret, encrypted at rest via application-layer envelope encryption.
    mfa_secret: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    roles: Mapped[list["Role"]] = relationship(  # noqa: F821
        secondary="user_roles", back_populates="users", lazy="selectin"
    )

    @property
    def mfa_enrolled(self) -> bool:
        return self.mfa_secret is not None
