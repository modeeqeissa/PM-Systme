"""Unit assignment history — FR-HR-02.

officers.unit_id and this history are kept in sync by app.services.assignments
.reassign, the single place either ever changes (also used by officer
creation and transfer approval).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Assignment, Officer, Unit
from app.schemas import AssignmentCreate, AssignmentOut
from app.services.assignments import reassign

router = APIRouter(prefix="/officers/{officer_id}/assignments", tags=["assignments"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=AssignmentOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.assignment.write"},
        404: {"description": "No officer with that id, or unit_id does not exist"},
    },
)
async def record_assignment(
    officer_id: uuid.UUID,
    payload: AssignmentCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.assignment.write")),
) -> AssignmentOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    unit = await session.get(Unit, payload.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="unit_id does not exist")

    assignment = await reassign(
        session, officer, unit_id=payload.unit_id, start_date=payload.start_date
    )

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="AssignmentRecorded",
        aggregate_type="assignment",
        aggregate_id=assignment.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "assignment_id": str(assignment.id),
            "officer_id": str(officer_id),
            "unit_id": str(assignment.unit_id),
            "start_date": assignment.start_date.isoformat(),
        },
    )
    return AssignmentOut.model_validate(assignment)


@router.get(
    "",
    response_model=list[AssignmentOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.assignment.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_assignments(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.assignment.read")),
) -> list[AssignmentOut]:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(Assignment)
        .where(Assignment.officer_id == officer_id)
        .order_by(Assignment.start_date.desc())
    )
    rows = (await session.scalars(q)).all()
    return [AssignmentOut.model_validate(a) for a in rows]
