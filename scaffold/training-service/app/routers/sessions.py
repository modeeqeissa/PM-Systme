"""Scheduled course sessions + per-officer attendance — docs §9.3.5.

A `session` is a concrete instance of a course (date, location, instructor,
capacity). `attendance` is one row per officer per session, moving
registered -> attended / absent. Gated on `training.cert.*` (this service's
domain-wide read/write code — see materials.py).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Attendance, Course, Session
from app.schemas import (
    AttendanceCreate,
    AttendanceOut,
    AttendanceStatusUpdate,
    SessionCreate,
    SessionOut,
    SessionUpdate,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
attendance_router = APIRouter(prefix="/attendance", tags=["attendance"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=SessionOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "course_id does not exist"},
    },
)
async def schedule_session(
    payload: SessionCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> SessionOut:
    if await session.get(Course, payload.course_id) is None:
        raise HTTPException(status_code=404, detail="course_id does not exist")

    row = Session(
        course_id=payload.course_id,
        scheduled_at=payload.scheduled_at,
        location=payload.location,
        instructor_officer_id=payload.instructor_officer_id,
        capacity=payload.capacity,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="SessionScheduled",
        aggregate_type="training_session",
        aggregate_id=row.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "session_id": str(row.id),
            "course_id": row.course_id,
            "scheduled_at": row.scheduled_at.isoformat(),
        },
    )
    return SessionOut.model_validate(row)


@router.get(
    "",
    response_model=list[SessionOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
    },
)
async def list_sessions(
    course_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[SessionOut]:
    q = select(Session).order_by(Session.scheduled_at)
    if course_id is not None:
        q = q.where(Session.course_id == course_id)
    rows = (await session.scalars(q)).all()
    return [SessionOut.model_validate(s) for s in rows]


@router.get(
    "/{session_id}",
    response_model=SessionOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No session with that id"},
    },
)
async def get_session_(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> SessionOut:
    row = await session.get(Session, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No session with that id")
    return SessionOut.model_validate(row)


@router.patch(
    "/{session_id}",
    response_model=SessionOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No session with that id"},
    },
)
async def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> SessionOut:
    row = await session.get(Session, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No session with that id")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return SessionOut.model_validate(row)
    for key, value in changes.items():
        setattr(row, key, value)
    await session.flush()
    await session.refresh(row)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="SessionUpdated",
        aggregate_type="training_session",
        aggregate_id=row.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"session_id": str(row.id), "changed_fields": sorted(changes)},
    )
    return SessionOut.model_validate(row)


# --- Attendance -----------------------------------------------------------
@router.get(
    "/{session_id}/attendance",
    response_model=list[AttendanceOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No session with that id"},
    },
)
async def list_session_attendance(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[AttendanceOut]:
    if await session.get(Session, session_id) is None:
        raise HTTPException(status_code=404, detail="No session with that id")
    rows = (
        await session.scalars(
            select(Attendance)
            .where(Attendance.session_id == session_id)
            .order_by(Attendance.officer_id)
        )
    ).all()
    return [AttendanceOut.model_validate(a) for a in rows]


@router.post(
    "/{session_id}/attendance",
    response_model=AttendanceOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No session with that id"},
        409: {"description": "That officer is already on this session's attendance"},
    },
)
async def record_attendance(
    session_id: uuid.UUID,
    payload: AttendanceCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> AttendanceOut:
    if await session.get(Session, session_id) is None:
        raise HTTPException(status_code=404, detail="No session with that id")

    row = Attendance(
        session_id=session_id,
        officer_id=payload.officer_id,
        status=payload.status.value,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:  # uq_attendance_session_officer
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="That officer is already on this session's attendance",
        )
    await session.refresh(row)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="AttendanceRecorded",
        aggregate_type="attendance",
        aggregate_id=row.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "attendance_id": str(row.id),
            "session_id": str(session_id),
            "officer_id": str(row.officer_id),
            "status": row.status,
        },
    )
    return AttendanceOut.model_validate(row)


@attendance_router.patch(
    "/{attendance_id}",
    response_model=AttendanceOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No attendance record with that id"},
    },
)
async def update_attendance_status(
    attendance_id: uuid.UUID,
    payload: AttendanceStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> AttendanceOut:
    row = await session.get(Attendance, attendance_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No attendance record with that id")

    from_status = row.status
    row.status = payload.status.value
    await session.flush()
    await session.refresh(row)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="AttendanceStatusChanged",
        aggregate_type="attendance",
        aggregate_id=row.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "attendance_id": str(row.id),
            "session_id": str(row.session_id),
            "officer_id": str(row.officer_id),
            "from_status": from_status,
            "to_status": row.status,
        },
    )
    return AttendanceOut.model_validate(row)
