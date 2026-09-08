"""Daily officer attendance — docs §9.3.6 revised.

One row per officer per day (present/absent/late/excused), with optional clock
in/out times. Gated on `hr.attendance.{read,write}` (iam migration 0010),
following the per-domain permission pattern of the rest of hr-service.
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import HrAttendance, Officer
from app.schemas import HrAttendanceCreate, HrAttendanceOut, HrAttendanceUpdate

by_officer_router = APIRouter(
    prefix="/officers/{officer_id}/attendance", tags=["hr-attendance"]
)
router = APIRouter(prefix="/attendance", tags=["hr-attendance"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_officer_router.post(
    "",
    response_model=HrAttendanceOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.attendance.write"},
        404: {"description": "No officer with that id"},
        409: {"description": "That officer already has an attendance row for that date"},
    },
)
async def record_attendance(
    officer_id: uuid.UUID,
    payload: HrAttendanceCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.attendance.write")),
) -> HrAttendanceOut:
    if await session.get(Officer, officer_id) is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    row = HrAttendance(
        officer_id=officer_id,
        date=payload.date,
        status=payload.status.value,
        clock_in=payload.clock_in,
        clock_out=payload.clock_out,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:  # uq_hr_attendance_officer_date
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="That officer already has an attendance row for that date",
        )
    await session.refresh(row)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="HrAttendanceRecorded",
        aggregate_type="hr_attendance",
        aggregate_id=row.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "hr_attendance_id": str(row.id),
            "officer_id": str(officer_id),
            "date": row.date.isoformat(),
            "status": row.status,
        },
    )
    return HrAttendanceOut.model_validate(row)


@by_officer_router.get(
    "",
    response_model=list[HrAttendanceOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.attendance.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_officer_attendance(
    officer_id: uuid.UUID,
    from_: dt.date | None = Query(default=None, alias="from"),
    to: dt.date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.attendance.read")),
) -> list[HrAttendanceOut]:
    if await session.get(Officer, officer_id) is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(HrAttendance)
        .where(HrAttendance.officer_id == officer_id)
        .order_by(HrAttendance.date.desc())
    )
    if from_ is not None:
        q = q.where(HrAttendance.date >= from_)
    if to is not None:
        q = q.where(HrAttendance.date <= to)
    rows = (await session.scalars(q)).all()
    return [HrAttendanceOut.model_validate(r) for r in rows]


@router.patch(
    "/{attendance_id}",
    response_model=HrAttendanceOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.attendance.write"},
        404: {"description": "No attendance row with that id"},
    },
)
async def update_attendance(
    attendance_id: uuid.UUID,
    payload: HrAttendanceUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.attendance.write")),
) -> HrAttendanceOut:
    row = await session.get(HrAttendance, attendance_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No attendance row with that id")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return HrAttendanceOut.model_validate(row)
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
    for key, value in changes.items():
        setattr(row, key, value)
    await session.flush()
    await session.refresh(row)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="HrAttendanceUpdated",
        aggregate_type="hr_attendance",
        aggregate_id=row.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "hr_attendance_id": str(row.id),
            "officer_id": str(row.officer_id),
            "changed_fields": sorted(changes),
            "status": row.status,
        },
    )
    return HrAttendanceOut.model_validate(row)
