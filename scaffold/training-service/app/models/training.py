import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
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


class Material(Base):
    """materials — a course document, object-storage-backed (docs §9.3.5)."""

    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # opaque object-storage key (app.services.materials_store), same pattern as
    # evidence_items.storage_ref.
    file_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class Session(Base):
    """sessions — a scheduled instance of a course (docs §9.3.5)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), nullable=False
    )
    scheduled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(200))
    # logical FK -> hr_db.officers.id
    instructor_officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    capacity: Mapped[int | None] = mapped_column(Integer)


class Attendance(Base):
    """attendance — one row per officer per session (docs §9.3.5)."""

    __tablename__ = "attendance"
    __table_args__ = (
        CheckConstraint(
            "status IN ('registered','attended','absent')", name="ck_attendance_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # logical FK -> hr_db.officers.id
    officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="registered"
    )


class Assessment(Base):
    """assessments — a gradeable test attached to a course (docs §9.3.5)."""

    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    passing_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)


class AssessmentResult(Base):
    """assessment_results — a graded attempt; `passed` is derived from the
    assessment's passing_score at grading time (docs §9.3.5)."""

    __tablename__ = "assessment_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    # logical FK -> hr_db.officers.id
    officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    taken_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
