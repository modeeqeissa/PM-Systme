"""Meeting minutes (1:1 per meeting) and decisions (docs §9.3.4).

* meeting_minutes — one formal record per meeting; POST creates it (409 if it
  already exists), PATCH edits the content.
* decisions — formal resolutions made at a meeting, each with its own
  pending/implemented/abandoned lifecycle.

Every mutating handler enqueues a domain event in the same DB transaction
(transactional outbox); audit-service consumes those into the hash-chained
audit log.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Decision, Meeting, MeetingMinutes
from app.schemas import (
    DecisionCreate,
    DecisionOut,
    DecisionStatusUpdate,
    MeetingMinutesCreate,
    MeetingMinutesOut,
    MeetingMinutesUpdate,
)

minutes_router = APIRouter(
    prefix="/meetings/{meeting_id}/minutes", tags=["meeting-minutes"]
)
decisions_by_meeting_router = APIRouter(
    prefix="/meetings/{meeting_id}/decisions", tags=["decisions"]
)
decisions_router = APIRouter(prefix="/decisions", tags=["decisions"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


async def _require_meeting(session: AsyncSession, meeting_id: uuid.UUID) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="No meeting with that id")
    return meeting


# --- Meeting minutes --------------------------------------------------------
@minutes_router.get(
    "",
    response_model=MeetingMinutesOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No meeting with that id, or it has no minutes yet"},
    },
)
async def get_meeting_minutes(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> MeetingMinutesOut:
    await _require_meeting(session, meeting_id)
    minutes = await session.scalar(
        select(MeetingMinutes).where(MeetingMinutes.meeting_id == meeting_id)
    )
    if minutes is None:
        raise HTTPException(status_code=404, detail="This meeting has no minutes yet")
    return MeetingMinutesOut.model_validate(minutes)


@minutes_router.post(
    "",
    response_model=MeetingMinutesOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No meeting with that id"},
        409: {"description": "This meeting already has minutes — PATCH to edit them"},
    },
)
async def record_meeting_minutes(
    meeting_id: uuid.UUID,
    payload: MeetingMinutesCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> MeetingMinutesOut:
    await _require_meeting(session, meeting_id)

    minutes = MeetingMinutes(
        meeting_id=meeting_id,
        content=payload.content,
        recorded_by=payload.recorded_by,
    )
    session.add(minutes)
    try:
        await session.flush()
    except IntegrityError:  # UNIQUE(meeting_id) — minutes already recorded
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This meeting already has minutes — PATCH to edit them",
        )
    await session.refresh(minutes)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="MeetingMinutesRecorded",
        aggregate_type="meeting_minutes",
        aggregate_id=minutes.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "meeting_minutes_id": str(minutes.id),
            "meeting_id": str(meeting_id),
            "recorded_by": str(minutes.recorded_by),
        },
    )
    return MeetingMinutesOut.model_validate(minutes)


@minutes_router.patch(
    "",
    response_model=MeetingMinutesOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No meeting with that id, or it has no minutes yet"},
    },
)
async def update_meeting_minutes(
    meeting_id: uuid.UUID,
    payload: MeetingMinutesUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> MeetingMinutesOut:
    await _require_meeting(session, meeting_id)
    minutes = await session.scalar(
        select(MeetingMinutes).where(MeetingMinutes.meeting_id == meeting_id)
    )
    if minutes is None:
        raise HTTPException(status_code=404, detail="This meeting has no minutes yet")

    minutes.content = payload.content
    await session.flush()
    await session.refresh(minutes)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="MeetingMinutesUpdated",
        aggregate_type="meeting_minutes",
        aggregate_id=minutes.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "meeting_minutes_id": str(minutes.id),
            "meeting_id": str(meeting_id),
        },
    )
    return MeetingMinutesOut.model_validate(minutes)


# --- Decisions ------------------------------------------------------------
@decisions_by_meeting_router.get(
    "",
    response_model=list[DecisionOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No meeting with that id"},
    },
)
async def list_meeting_decisions(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[DecisionOut]:
    await _require_meeting(session, meeting_id)
    rows = (
        await session.scalars(
            select(Decision).where(Decision.meeting_id == meeting_id).order_by(Decision.id)
        )
    ).all()
    return [DecisionOut.model_validate(d) for d in rows]


@decisions_by_meeting_router.post(
    "",
    response_model=DecisionOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No meeting with that id"},
    },
)
async def record_decision(
    meeting_id: uuid.UUID,
    payload: DecisionCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> DecisionOut:
    await _require_meeting(session, meeting_id)

    decision = Decision(meeting_id=meeting_id, description=payload.description)
    session.add(decision)
    await session.flush()
    await session.refresh(decision)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="DecisionRecorded",
        aggregate_type="decision",
        aggregate_id=decision.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "decision_id": str(decision.id),
            "meeting_id": str(meeting_id),
            "status": decision.status,
        },
    )
    return DecisionOut.model_validate(decision)


@decisions_router.get(
    "/{decision_id}",
    response_model=DecisionOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No decision with that id"},
    },
)
async def get_decision(
    decision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> DecisionOut:
    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="No decision with that id")
    return DecisionOut.model_validate(decision)


@decisions_router.patch(
    "/{decision_id}",
    response_model=DecisionOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No decision with that id"},
    },
)
async def update_decision_status(
    decision_id: uuid.UUID,
    payload: DecisionStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> DecisionOut:
    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="No decision with that id")

    from_status = decision.status
    decision.status = payload.status.value
    await session.flush()
    await session.refresh(decision)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="DecisionStatusChanged",
        aggregate_type="decision",
        aggregate_id=decision.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "decision_id": str(decision.id),
            "meeting_id": str(decision.meeting_id),
            "from_status": from_status,
            "to_status": decision.status,
        },
    )
    return DecisionOut.model_validate(decision)
