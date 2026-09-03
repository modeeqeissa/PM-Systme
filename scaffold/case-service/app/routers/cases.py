"""Case lifecycle + arrests — FR-CASE-02, FR-CASE-03.

Every mutating handler enqueues a domain event in the same DB transaction
(transactional outbox, SRS §3.4). audit-service consumes those events and writes
the independent, hash-chained audit-log entry (CLAUDE.md rule 3 / FR-AUD-01).
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Arrest, Case, Incident
from app.schemas import ArrestCreate, ArrestOut, CaseCreate, CaseOut, CaseStatusUpdate
from app.services.case_status import can_transition

router = APIRouter(prefix="/cases", tags=["cases"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=CaseOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.write"},
        404: {"description": "incident_id does not exist"},
    },
)
async def open_case(
    payload: CaseCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.write")),
) -> CaseOut:
    """Escalate an incident into a formal case with a sequential number (FR-CASE-02)."""
    incident_type: str | None = None
    station_id: str | None = None
    if payload.incident_id is not None:
        incident = await session.get(Incident, payload.incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="incident_id does not exist")
        incident_type = incident.incident_type
        station_id = str(incident.station_id)

    seq = await session.scalar(select(func.nextval("case_number_seq")))
    case_number = f"CASE-{dt.datetime.now(dt.timezone.utc).year}-{seq:06d}"

    case = Case(
        case_number=case_number,
        incident_id=payload.incident_id,
        status="open",
        lead_officer_id=payload.lead_officer_id,
    )
    session.add(case)
    await session.flush()
    await session.refresh(case)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CaseOpened",
        aggregate_type="case",
        aggregate_id=case.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "case_id": str(case.id),
            "case_number": case.case_number,
            "incident_id": str(case.incident_id) if case.incident_id else None,
            "incident_type": incident_type,
            "station_id": station_id,
            "lead_officer_id": str(case.lead_officer_id),
            "opened_at": case.opened_at.isoformat(),
        },
    )
    return CaseOut.model_validate(case)


@router.get(
    "/{case_id}",
    response_model=CaseOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "RBAC scope denied"},
        404: {"description": "Not found"},
    },
)
async def get_case(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("case.read")),
) -> CaseOut:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut.model_validate(case)


@router.patch(
    "/{case_id}/status",
    response_model=CaseOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.write"},
        404: {"description": "No case with that id"},
        409: {"description": "Invalid status transition"},
    },
)
async def update_case_status(
    case_id: uuid.UUID,
    payload: CaseStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.write")),
) -> CaseOut:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    from_status = case.status
    target = payload.status.value
    if not can_transition(from_status, target):
        raise HTTPException(
            status_code=409,
            detail=f"Invalid status transition: {from_status} -> {target}",
        )

    case.status = target
    if target == "closed" and case.closed_at is None:
        case.closed_at = dt.datetime.now(dt.timezone.utc)
    await session.flush()
    await session.refresh(case)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CaseStatusChanged",
        aggregate_type="case",
        aggregate_id=case.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "case_id": str(case.id),
            "from_status": from_status,
            "to_status": target,
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
        },
    )
    return CaseOut.model_validate(case)


@router.post(
    "/{case_id}/arrests",
    response_model=ArrestOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.write"},
        404: {"description": "No case with that id"},
    },
)
async def record_arrest(
    case_id: uuid.UUID,
    payload: ArrestCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.write")),
) -> ArrestOut:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="No case with that id")

    arrest = Arrest(
        case_id=case_id,
        officer_id=payload.officer_id,
        suspect_id=payload.suspect_id,
        arrest_date=payload.arrest_date,
        location=payload.location,
        legal_basis=payload.legal_basis,
    )
    session.add(arrest)
    await session.flush()
    await session.refresh(arrest)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="ArrestRecorded",
        aggregate_type="arrest",
        aggregate_id=arrest.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "arrest_id": str(arrest.id),
            "case_id": str(case_id),
            "officer_id": str(arrest.officer_id),
            "suspect_id": str(arrest.suspect_id),
            "arrest_date": arrest.arrest_date.isoformat(),
        },
    )
    return ArrestOut.model_validate(arrest)
