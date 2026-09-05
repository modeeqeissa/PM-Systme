"""Community concerns — FR-COMM-02.

docs Section 9.3.4 gives concerns only category/status/meeting_id — no
free-text description and no reporter identity — so a concern here records
only "a concern of this category was raised" (optionally linked to a
meeting), not any narrative detail. Flagged rather than inventing a
description column the schema doesn't define (CLAUDE.md rule 5).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Concern, Meeting
from app.schemas import ConcernCreate, ConcernOut, ConcernStatus, ConcernStatusUpdate

router = APIRouter(prefix="/concerns", tags=["concerns"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=ConcernOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "meeting_id does not exist"},
    },
)
async def log_concern(
    payload: ConcernCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> ConcernOut:
    if payload.meeting_id is not None:
        meeting = await session.get(Meeting, payload.meeting_id)
        if meeting is None:
            raise HTTPException(status_code=404, detail="meeting_id does not exist")

    concern = Concern(meeting_id=payload.meeting_id, category=payload.category)
    session.add(concern)
    await session.flush()
    await session.refresh(concern)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="ConcernLogged",
        aggregate_type="concern",
        aggregate_id=concern.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "concern_id": str(concern.id),
            "meeting_id": str(concern.meeting_id) if concern.meeting_id else None,
            "category": concern.category,
        },
    )
    return ConcernOut.model_validate(concern)


@router.get(
    "",
    response_model=list[ConcernOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks community.read"}},
)
async def list_concerns(
    meeting_id: uuid.UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    status_: ConcernStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[ConcernOut]:
    q = select(Concern)
    if meeting_id is not None:
        q = q.where(Concern.meeting_id == meeting_id)
    if category is not None:
        q = q.where(Concern.category == category)
    if status_ is not None:
        q = q.where(Concern.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [ConcernOut.model_validate(c) for c in rows]


@router.get(
    "/{concern_id}",
    response_model=ConcernOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No concern with that id"},
    },
)
async def get_concern(
    concern_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> ConcernOut:
    concern = await session.get(Concern, concern_id)
    if concern is None:
        raise HTTPException(status_code=404, detail="No concern with that id")
    return ConcernOut.model_validate(concern)


@router.patch(
    "/{concern_id}",
    response_model=ConcernOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No concern with that id"},
    },
)
async def update_concern_status(
    concern_id: uuid.UUID,
    payload: ConcernStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> ConcernOut:
    concern = await session.get(Concern, concern_id)
    if concern is None:
        raise HTTPException(status_code=404, detail="No concern with that id")

    from_status = concern.status
    concern.status = payload.status.value
    await session.flush()
    await session.refresh(concern)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="ConcernStatusChanged",
        aggregate_type="concern",
        aggregate_id=concern.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "concern_id": str(concern.id),
            "from_status": from_status,
            "to_status": concern.status,
        },
    )
    return ConcernOut.model_validate(concern)
