import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # e.g. CAD, NCDB, COURTS, JAIL
    system_name: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class ExternalSystemLog(Base):
    __tablename__ = "external_system_logs"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound','outbound')",
            name="ck_external_system_logs_direction",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_name: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # trace id linking request/response across services
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
