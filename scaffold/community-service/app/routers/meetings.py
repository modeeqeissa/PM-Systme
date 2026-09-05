"""Community meetings — FR-COMM-01.

Every mutating handler enqueues a domain event in the same DB transaction
(transactional outbox, SRS §3.4); audit-service consumes those events into
the independent, hash-chained audit log (CLAUDE.md rule 3 / FR-AUD-01).

FR-COMM-01 also asks to capture an "attendee summary", but docs Section 9.3.4's
meetings table has no column for it — not implemented; flagged rather than
inventing a field the schema doesn't define (CLAUDE.md rule 5).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Meeting
from app.schemas import MeetingCreate, MeetingOut

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=MeetingOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
    },
)
async def log_meeting(
    payload: MeetingCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> MeetingOut:
    meeting = Meeting(
        station_id=payload.station_id,
        facilitator_id=payload.facilitator_id,
        meeting_date=payload.meeting_date,
        location=payload.location,
    )
    session.add(meeting)
    await session.flush()
    await session.refresh(meeting)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="MeetingLogged",
        aggregate_type="meeting",
        aggregate_id=meeting.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "meeting_id": str(meeting.id),
            "station_id": str(meeting.station_id),
            "facilitator_id": str(meeting.facilitator_id),
            "meeting_date": meeting.meeting_date.isoformat(),
        },
    )
    return MeetingOut.model_validate(meeting)


@router.get(
    "",
    response_model=list[MeetingOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks community.read"}},
)
async def list_meetings(
    station_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[MeetingOut]:
    q = select(Meeting).order_by(Meeting.meeting_date.desc())
    if station_id is not None:
        q = q.where(Meeting.station_id == station_id)
    rows = (await session.scalars(q)).all()
    return [MeetingOut.model_validate(m) for m in rows]


@router.get(
    "/{meeting_id}",
    response_model=MeetingOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No meeting with that id"},
    },
)
async def get_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> MeetingOut:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="No meeting with that id")
    return MeetingOut.model_validate(meeting)
