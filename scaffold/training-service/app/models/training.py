import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    validity_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )


class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), nullable=False
    )


class OfficerCertification(Base):
    __tablename__ = "officer_certifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','expiring_soon','expired')",
            name="ck_officer_certifications_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # logical FK -> hr_db.officers.id
    officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    certification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certifications.id"), nullable=False
    )
    issued_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    expires_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
