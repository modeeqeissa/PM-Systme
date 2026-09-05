"""GET /dashboard/kpis — read-only KPI snapshot from the CQRS projections."""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.models import MvCrimeTrends, MvEvidenceIntegrity, MvStationCaseKpis
from app.schemas import (
    CaseKpis,
    CrimeTrendBucket,
    EvidenceIntegrityKpis,
    KpiSnapshot,
    UnitReadiness,
)
from app.services.unit_readiness import unit_readiness

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_MIN_DAY = dt.date(1900, 1, 1)
_MAX_DAY = dt.date(9999, 12, 31)


@router.get(
    "/kpis",
    response_model=KpiSnapshot,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks dashboard.view"},
    },
)
async def kpi_snapshot(
    station_id: uuid.UUID | None = Query(default=None),
    from_: dt.date | None = Query(default=None, alias="from"),
    to: dt.date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("dashboard.view")),
) -> KpiSnapshot:
    lo, hi = from_ or _MIN_DAY, to or _MAX_DAY

    ck = select(
        func.coalesce(func.sum(MvStationCaseKpis.open_cases), 0),
        func.coalesce(func.sum(MvStationCaseKpis.closed_cases), 0),
        func.coalesce(func.sum(MvStationCaseKpis.arrests_recorded), 0),
        func.coalesce(func.sum(MvStationCaseKpis.sum_age_days), 0),
    ).where(MvStationCaseKpis.day.between(lo, hi))
    if station_id is not None:
        ck = ck.where(MvStationCaseKpis.station_id == station_id)
    opened, closed, arrests, sum_age = (await session.execute(ck)).one()
    closed = int(closed)
    cases = CaseKpis(
        opened=int(opened),
        closed=closed,
        arrests_recorded=int(arrests),
        avg_case_age_days=(float(sum_age) / closed) if closed else None,
    )

    ct = (
        select(
            MvCrimeTrends.month, MvCrimeTrends.incident_type, MvCrimeTrends.count
        )
        .where(MvCrimeTrends.month.between(lo.replace(day=1), hi))
        .order_by(MvCrimeTrends.month, MvCrimeTrends.count.desc())
    )
    if station_id is not None:
        ct = ct.where(MvCrimeTrends.station_id == station_id)
    trends = [
        CrimeTrendBucket(
            month=m, incident_type=None if it == "unknown" else it, count=int(c)
        )
        for m, it, c in (await session.execute(ct)).all()
    ]

    # evidence integrity has no station key (see model docstring) - always force-wide
    ei = select(
        func.coalesce(func.sum(MvEvidenceIntegrity.evidence_logged), 0),
        func.coalesce(func.sum(MvEvidenceIntegrity.pending_transfer_ack_count), 0),
        func.coalesce(func.sum(MvEvidenceIntegrity.hash_mismatch_count), 0),
    )
    logged, pending, mism = (await session.execute(ei)).one()

    readiness = [
        UnitReadiness(**row)
        for row in await unit_readiness(session, station_id=station_id)
    ]

    return KpiSnapshot(
        station_id=station_id,
        as_of=dt.datetime.now(dt.timezone.utc),
        cases=cases,
        crime_trends=trends,
        evidence_integrity=EvidenceIntegrityKpis(
            evidence_logged=int(logged),
            pending_transfer_ack=int(pending),
            hash_mismatches=int(mism),
        ),
        unit_readiness=readiness,
    )
