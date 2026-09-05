"""Officer master profile — FR-HR-01.

Every mutating handler enqueues a domain event in the same DB transaction
(transactional outbox, SRS §3.4); audit-service consumes those events into
the independent, hash-chained audit log (CLAUDE.md rule 3 / FR-AUD-01).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Officer, Unit
from app.schemas import OfficerCreate, OfficerOut, OfficerStatus, OfficerUpdate
from app.services.assignments import reassign

router = APIRouter(prefix="/officers", tags=["officers"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


def _emit_supervisor_changed(session, officer, previous, actor_id, actor_role) -> None:
    """OfficerSupervisorChanged — notification-service consumes it to know an
    officer's supervisor for FR-COMM-04 escalation. Payload carries the new
    (and previous) supervisor_id so a downstream map can be kept current."""
    enqueue(
        session,
        event_type="OfficerSupervisorChanged",
        aggregate_type="officer",
        aggregate_id=officer.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "officer_id": str(officer.id),
            "supervisor_id": str(officer.supervisor_id) if officer.supervisor_id else None,
            "previous_supervisor_id": str(previous) if previous else None,
        },
    )


@router.post(
    "",
    response_model=OfficerOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.officer.write"},
        404: {"description": "unit_id does not exist"},
        409: {"description": "user_id or badge_number already in use"},
    },
)
async def create_officer(
    payload: OfficerCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.officer.write")),
) -> OfficerOut:
    unit = await session.get(Unit, payload.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="unit_id does not exist")

    if payload.supervisor_id is not None:
        if await session.get(Officer, payload.supervisor_id) is None:
            raise HTTPException(status_code=404, detail="supervisor_id does not exist")

    officer = Officer(
        user_id=payload.user_id,
        badge_number=payload.badge_number,
        rank=payload.rank,
        unit_id=payload.unit_id,
        hire_date=payload.hire_date,
        supervisor_id=payload.supervisor_id,
        status=payload.status.value,
    )
    session.add(officer)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="user_id or badge_number already in use"
        )
    await session.refresh(officer)

    # Officer profile always carries a current unit -> the assignment history
    # starts here too (FR-HR-02), via the one place unit_id ever changes.
    await reassign(session, officer, unit_id=payload.unit_id, start_date=payload.hire_date)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="OfficerCreated",
        aggregate_type="officer",
        aggregate_id=officer.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "officer_id": str(officer.id),
            "user_id": str(officer.user_id),
            "badge_number": officer.badge_number,
            "rank": officer.rank,
            "unit_id": str(officer.unit_id),
            "supervisor_id": str(officer.supervisor_id) if officer.supervisor_id else None,
            "status": officer.status,
        },
    )
    if officer.supervisor_id is not None:
        _emit_supervisor_changed(session, officer, None, actor_id, actor_role)
    return OfficerOut.model_validate(officer)


@router.get(
    "",
    response_model=list[OfficerOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.officer.read"},
    },
)
async def list_officers(
    unit_id: uuid.UUID | None = Query(default=None),
    status_: OfficerStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.officer.read")),
) -> list[OfficerOut]:
    q = select(Officer).order_by(Officer.badge_number).limit(limit).offset(offset)
    if unit_id is not None:
        q = q.where(Officer.unit_id == unit_id)
    if status_ is not None:
        q = q.where(Officer.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [OfficerOut.model_validate(o) for o in rows]


@router.get(
    "/{officer_id}",
    response_model=OfficerOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.officer.read"},
        404: {"description": "No officer with that id"},
    },
)
async def get_officer(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.officer.read")),
) -> OfficerOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    return OfficerOut.model_validate(officer)


@router.patch(
    "/{officer_id}",
    response_model=OfficerOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.officer.write"},
        404: {"description": "No officer with that id"},
        409: {"description": "badge_number already in use"},
    },
)
async def update_officer(
    officer_id: uuid.UUID,
    payload: OfficerUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.officer.write")),
) -> OfficerOut:
    """Corrections to badge_number/hire_date/status. rank and unit_id are not
    editable here — see app.schemas.hr.OfficerUpdate."""
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    updated_fields: list[str] = []
    if payload.badge_number is not None:
        officer.badge_number = payload.badge_number
        updated_fields.append("badge_number")
    if payload.hire_date is not None:
        officer.hire_date = payload.hire_date
        updated_fields.append("hire_date")
    if payload.status is not None:
        officer.status = payload.status.value
        updated_fields.append("status")

    # supervisor_id: "supervisor_id": null in the body clears it, absent leaves
    # it — distinguished via model_fields_set.
    supervisor_changed = False
    previous_supervisor_id = officer.supervisor_id
    if "supervisor_id" in payload.model_fields_set:
        if payload.supervisor_id is not None and payload.supervisor_id != officer.id:
            if await session.get(Officer, payload.supervisor_id) is None:
                raise HTTPException(status_code=404, detail="supervisor_id does not exist")
        if payload.supervisor_id == officer.id:
            raise HTTPException(status_code=422, detail="an officer cannot supervise themselves")
        if payload.supervisor_id != officer.supervisor_id:
            officer.supervisor_id = payload.supervisor_id
            updated_fields.append("supervisor_id")
            supervisor_changed = True

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="badge_number already in use")
    await session.refresh(officer)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="OfficerUpdated",
        aggregate_type="officer",
        aggregate_id=officer.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"officer_id": str(officer.id), "fields": updated_fields},
    )
    if supervisor_changed:
        _emit_supervisor_changed(
            session, officer, previous_supervisor_id, actor_id, actor_role
        )
    return OfficerOut.model_validate(officer)
