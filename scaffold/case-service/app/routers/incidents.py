"""POST /incidents — FR-CASE-01, FR-CASE-10 (offline-sync idempotency).

Creating an incident enqueues an IncidentReported domain event in the same
transaction (transactional outbox, SRS §3.4); audit-service consumes it and
writes the independent audit-log entry (CLAUDE.md rule 3 / FR-AUD-01). An
idempotent replay (200) does not re-emit.
"""
import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Incident
from app.schemas import IncidentCreate, IncidentOut

router = APIRouter(tags=["incidents"])


@router.post(
    "/incidents",
    response_model=IncidentOut,
    status_code=201,
    responses={
        200: {"model": IncidentOut, "description": "Idempotent replay"},
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.write"},
    },
)
async def create_incident(
    payload: IncidentCreate,
    response: Response,
    idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.write")),
) -> IncidentOut:
    """Create an incident, deduping on the ``Idempotency-Key`` header.

    First call for a key -> 201 with the new record. Any later call with the same
    key -> 200 with the record created the first time (payload is not re-applied).
    """
    existing = await session.scalar(
        select(Incident).where(Incident.client_sync_id == idempotency_key)
    )
    if existing is not None:
        response.status_code = 200
        return IncidentOut.model_validate(existing)

    incident = Incident(
        reported_by=payload.reported_by,
        incident_type=payload.incident_type,
        description=payload.description,
        latitude=payload.latitude,
        longitude=payload.longitude,
        station_id=payload.station_id,
        reported_at=payload.reported_at,
        client_sync_id=idempotency_key,
    )
    session.add(incident)
    try:
        await session.flush()
    except IntegrityError:
        # Concurrent request won the race on the unique client_sync_id.
        await session.rollback()
        existing = await session.scalar(
            select(Incident).where(Incident.client_sync_id == idempotency_key)
        )
        response.status_code = 200
        return IncidentOut.model_validate(existing)

    await session.refresh(incident)

    enqueue(
        session,
        event_type="IncidentReported",
        aggregate_type="incident",
        aggregate_id=incident.id,
        actor_id=claims.get("sub"),
        actor_role=",".join(claims.get("roles") or []),
        payload={
            "incident_id": str(incident.id),
            "reported_by": str(incident.reported_by),
            "incident_type": incident.incident_type,
            "station_id": str(incident.station_id),
            "reported_at": incident.reported_at.isoformat(),
        },
    )
    return IncidentOut.model_validate(incident)
