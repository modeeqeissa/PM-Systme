import datetime as dt
import uuid

from sqlalchemy import BigInteger, Date, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConsumedEvent(Base):
    """Idempotency ledger — one row per Kafka event_id already applied (SRS §9.4)."""

    __tablename__ = "dash_consumed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DashCase(Base):
    """Minimal case dimension the consumer maintains so close/arrest events (which
    don't carry station or open time) can still be attributed and aged."""

    __tablename__ = "dash_case"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_type: Mapped[str | None] = mapped_column(String(50))
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed: Mapped[bool] = mapped_column(nullable=False, server_default="false")


class MvStationCaseKpis(Base):
    """open_cases / closed_cases / arrests per station per day (SRS §9.3.7)."""

    __tablename__ = "mv_station_case_kpis"

    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open_cases: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    closed_cases: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    arrests_recorded: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    # running sum of (closed_at - opened_at) in days, for avg_case_age_days
    sum_age_days: Mapped[float] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="0"
    )


class MvCrimeTrends(Base):
    """Incident counts by type, station and month (SRS §9.3.7), from CaseOpened."""

    __tablename__ = "mv_crime_trends"

    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    month: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class MvEvidenceIntegrity(Base):
    """Evidence integrity signals per evidence item.

    SRS §9.3.7 keys these per station, but neither evidence_items (§9.3.3) nor the
    EvidenceLogged / CustodyEventRecorded / EvidenceHashMismatch events carry a
    station, so this is keyed per evidence_id. Feeds: EvidenceLogged ->
    evidence_logged; CustodyEventRecorded (transferred, no ack) ->
    pending_transfer_ack_count; EvidenceHashMismatch -> hash_mismatch_count.
    """

    __tablename__ = "mv_evidence_integrity"

    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    evidence_logged: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    pending_transfer_ack_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    hash_mismatch_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
