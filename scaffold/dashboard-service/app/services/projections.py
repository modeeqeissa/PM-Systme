"""Apply a domain event to the CQRS read models (docs Section 9.3.7)."""
import datetime as dt
import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import NIL_UUID
from app.models import (
    DashCase,
    DashLeave,
    DashOfficer,
    DashOfficerCert,
    DashTransfer,
    DashUnit,
    MvCrimeTrends,
    MvEvidenceIntegrity,
    MvStationCaseKpis,
)


def _parse_ts(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    return dt.datetime.fromisoformat(value)


async def _upsert_officer_unit(session: AsyncSession, officer_id: str, unit_id: str) -> None:
    stmt = insert(DashOfficer).values(
        officer_id=uuid.UUID(officer_id), unit_id=uuid.UUID(unit_id)
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["officer_id"], set_={"unit_id": stmt.excluded.unit_id}
        )
    )


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

    # --- FR-DASH-02 mv_unit_readiness dimensions --------------------------
    elif event_type == "UnitCreated":
        stmt = insert(DashUnit).values(
            unit_id=uuid.UUID(payload["unit_id"]),
            station_id=uuid.UUID(str(payload.get("station_id") or NIL_UUID)),
            name=payload.get("name"),
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["unit_id"],
                set_={"station_id": stmt.excluded.station_id, "name": stmt.excluded.name},
            )
        )

    elif event_type == "OfficerCreated":
        if payload.get("unit_id"):
            await _upsert_officer_unit(session, payload["officer_id"], payload["unit_id"])

    elif event_type == "AssignmentRecorded":
        await _upsert_officer_unit(session, payload["officer_id"], payload["unit_id"])

    elif event_type == "TransferRequested":
        if payload.get("to_unit_id"):
            await session.execute(
                insert(DashTransfer)
                .values(
                    transfer_id=uuid.UUID(payload["transfer_id"]),
                    to_unit_id=uuid.UUID(payload["to_unit_id"]),
                )
                .on_conflict_do_nothing(index_elements=["transfer_id"])
            )

    elif event_type == "TransferStatusChanged":
        if payload.get("to_status") == "approved":
            transfer = await session.get(
                DashTransfer, uuid.UUID(payload["transfer_id"])
            )
            if transfer is not None:
                await _upsert_officer_unit(
                    session, payload["officer_id"], str(transfer.to_unit_id)
                )

    elif event_type == "LeaveRequested":
        # start_date/end_date were added to the LeaveRequested payload with
        # hr-service migration 0004; a pre-0004 event without them can't feed
        # the date-relative on_leave_count, so it's skipped.
        if payload.get("start_date") and payload.get("end_date"):
            await session.execute(
                insert(DashLeave)
                .values(
                    leave_request_id=uuid.UUID(payload["leave_request_id"]),
                    officer_id=uuid.UUID(payload["officer_id"]),
                    start_date=dt.date.fromisoformat(payload["start_date"]),
                    end_date=dt.date.fromisoformat(payload["end_date"]),
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["leave_request_id"])
            )

    elif event_type == "LeaveStatusChanged":
        await session.execute(
            update(DashLeave)
            .where(DashLeave.leave_request_id == uuid.UUID(payload["leave_request_id"]))
            .values(status=payload["to_status"])
        )

    elif event_type == "OfficerCertificationIssued":
        stmt = insert(DashOfficerCert).values(
            officer_certification_id=uuid.UUID(payload["officer_certification_id"]),
            officer_id=uuid.UUID(payload["officer_id"]),
            status=payload["status"],
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["officer_certification_id"],
                set_={"status": stmt.excluded.status},
            )
        )

    elif event_type == "OfficerCertificationStatusChanged":
        await session.execute(
            update(DashOfficerCert)
            .where(
                DashOfficerCert.officer_certification_id
                == uuid.UUID(payload["officer_certification_id"])
            )
            .values(status=payload["to_status"])
        )
