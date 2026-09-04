"""Single place that keeps officers.unit_id and the assignments history in
sync (FR-HR-02) — used by officer creation, the direct assignment endpoint,
and transfer approval, so there's exactly one way an officer's current unit
ever changes.
"""
import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, Officer


async def reassign(
    session: AsyncSession,
    officer: Officer,
    *,
    unit_id: uuid.UUID,
    start_date: dt.date,
) -> Assignment:
    """Close the officer's open assignment (if any) and open a new one."""
    open_assignment = await session.scalar(
        select(Assignment)
        .where(Assignment.officer_id == officer.id, Assignment.end_date.is_(None))
        .order_by(Assignment.start_date.desc())
        .limit(1)
    )
    if open_assignment is not None and open_assignment.end_date is None:
        open_assignment.end_date = start_date

    assignment = Assignment(officer_id=officer.id, unit_id=unit_id, start_date=start_date)
    session.add(assignment)
    officer.unit_id = unit_id
    await session.flush()
    await session.refresh(assignment)
    return assignment
