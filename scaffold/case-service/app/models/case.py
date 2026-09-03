import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Case(Base):
    """cases — migration 0001 / docs Section 9.3.2."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    case_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="open"
    )
    lead_officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    opened_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class CaseOfficer(Base):
    __tablename__ = "case_officers"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True
    )
    officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role_on_case: Mapped[str] = mapped_column(String(30), nullable=False)


class Arrest(Base):
    __tablename__ = "arrests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False
    )
    officer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suspect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    arrest_date: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    location: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[str | None] = mapped_column(Text)


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    party_type: Mapped[str] = mapped_column(String(20), nullable=False)
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CourtProceeding(Base):
    __tablename__ = "court_proceedings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False
    )
    hearing_date: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    court_name: Mapped[str | None] = mapped_column(String(150))
    verdict: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
