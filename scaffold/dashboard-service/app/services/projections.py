"""Apply a domain event to the CQRS read models (docs Section 9.3.7)."""
import datetime as dt
import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import NIL_UUID
from app.models import (
    DashCase,
    MvCrimeTrends,
    MvEvidenceIntegrity,
    MvStationCaseKpis,
)


def _parse_ts(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    return dt.datetime.fromisoformat(value)


def _month_start(d: dt.date) -> dt.date:
    return d.replace(day=1)


async def _bump_case_kpis(session: AsyncSession, station_id, day: dt.date, **deltas):
    cols = {"station_id": station_id, "day": day, **deltas}
    stmt = insert(MvStationCaseKpis).values(**cols)
    stmt = stmt.on_conflict_do_update(
        index_elements=["station_id", "day"],
        set_={
            k: getattr(MvStationCaseKpis, k) + stmt.excluded[k] for k in deltas
        },
    )
    await session.execute(stmt)


async def _bump_crime_trends(session: AsyncSession, station_id, month: dt.date, itype: str):
    stmt = insert(MvCrimeTrends).values(
        station_id=station_id, month=month, incident_type=itype, count=1
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["station_id", "month", "incident_type"],
        set_={"count": MvCrimeTrends.count + stmt.excluded["count"]},
    )
    await session.execute(stmt)


async def _bump_evidence_integrity(session: AsyncSession, evidence_id, **deltas):
    stmt = insert(MvEvidenceIntegrity).values(evidence_id=evidence_id, **deltas)
    stmt = stmt.on_conflict_do_update(
        index_elements=["evidence_id"],
        set_={k: getattr(MvEvidenceIntegrity, k) + stmt.excluded[k] for k in deltas},
    )
    await session.execute(stmt)


async def apply_event(session: AsyncSession, envelope: dict) -> None:
    event_type = envelope.get("event_type")
    payload = envelope.get("payload") or {}
    occurred = _parse_ts(envelope.get("occurred_at"))

    if event_type == "CaseOpened":
        station_id = payload.get("station_id") or NIL_UUID
        incident_type = payload.get("incident_type") or "unknown"
        opened_at = _parse_ts(payload.get("opened_at"))
        dc = insert(DashCase).values(
            case_id=uuid.UUID(payload["case_id"]),
            station_id=uuid.UUID(str(station_id)),
            incident_type=payload.get("incident_type"),
            opened_at=opened_at,
            closed=False,
        )
        await session.execute(dc.on_conflict_do_nothing(index_elements=["case_id"]))
        await _bump_case_kpis(session, station_id, opened_at.date(), open_cases=1)
        await _bump_crime_trends(
            session, station_id, _month_start(opened_at.date()), incident_type
        )

    elif event_type == "CaseStatusChanged":
        if payload.get("to_status") != "closed":
            return
        case = await session.get(DashCase, uuid.UUID(payload["case_id"]))
        if case is None or case.closed:
            return
        closed_at = _parse_ts(payload.get("closed_at"))
        age_days = (closed_at - case.opened_at).total_seconds() / 86400.0
        case.closed = True
        await _bump_case_kpis(
            session,
            case.station_id,
            closed_at.date(),
            closed_cases=1,
            sum_age_days=age_days,
        )

    elif event_type == "ArrestRecorded":
        case = await session.get(DashCase, uuid.UUID(payload["case_id"]))
        if case is None:
            return
        await _bump_case_kpis(
            session, case.station_id, occurred.date(), arrests_recorded=1
        )

    elif event_type == "EvidenceLogged":
        await _bump_evidence_integrity(
            session, uuid.UUID(payload["evidence_id"]), evidence_logged=1
        )

    elif event_type == "CustodyEventRecorded":
        if payload.get("action") == "transferred" and not payload.get("acknowledgement"):
            await _bump_evidence_integrity(
                session,
                uuid.UUID(payload["evidence_id"]),
                pending_transfer_ack_count=1,
            )

    elif event_type == "EvidenceHashMismatch":
        await _bump_evidence_integrity(
            session, uuid.UUID(payload["evidence_id"]), hash_mismatch_count=1
        )
