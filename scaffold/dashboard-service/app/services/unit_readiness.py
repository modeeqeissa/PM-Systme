"""mv_unit_readiness computed at read time (docs Section 9.3.7, FR-DASH-02).

certified_officer_pct and on_leave_count per unit, from the dimension tables
app/services/projections.py maintains. Computed here rather than stored
because the on-leave figure is date-relative — an approved leave only counts
while today falls inside [start_date, end_date].

certified = an officer with at least one dash_officer_cert row whose status
is 'active' or 'expiring_soon' (i.e. not 'expired'); pct is over all
officers currently assigned to the unit.
"""
import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DashLeave, DashOfficer, DashOfficerCert, DashUnit

_CERTIFIED_STATUSES = ("active", "expiring_soon")


async def unit_readiness(
    session: AsyncSession, *, station_id: uuid.UUID | None = None, today: dt.date | None = None
) -> list[dict]:
    today = today or dt.date.today()

    units_q = select(DashUnit.unit_id, DashUnit.station_id, DashUnit.name)
    if station_id is not None:
        units_q = units_q.where(DashUnit.station_id == station_id)
    units = (await session.execute(units_q.order_by(DashUnit.name))).all()

    out: list[dict] = []
    for unit_id, st_id, name in units:
        total = await session.scalar(
            select(func.count()).select_from(DashOfficer).where(DashOfficer.unit_id == unit_id)
        )
        certified = await session.scalar(
            select(func.count(func.distinct(DashOfficer.officer_id)))
            .select_from(DashOfficer)
            .join(DashOfficerCert, DashOfficerCert.officer_id == DashOfficer.officer_id)
            .where(
                DashOfficer.unit_id == unit_id,
                DashOfficerCert.status.in_(_CERTIFIED_STATUSES),
            )
        )
        on_leave = await session.scalar(
            select(func.count(func.distinct(DashOfficer.officer_id)))
            .select_from(DashOfficer)
            .join(DashLeave, DashLeave.officer_id == DashOfficer.officer_id)
            .where(
                DashOfficer.unit_id == unit_id,
                DashLeave.status == "approved",
                DashLeave.start_date <= today,
                DashLeave.end_date >= today,
            )
        )
        out.append(
            {
                "unit_id": unit_id,
                "station_id": st_id,
                "unit_name": name,
                "total_officers": total,
                "certified_officer_pct": (100.0 * certified / total) if total else None,
                "on_leave_count": on_leave,
            }
        )
    return out
