"""GET/POST /evidence/{id}/custody — the append-only chain of custody (FR-EVID-03/04).

Recording a custody event enqueues a CustodyEventRecorded domain event
(transactional outbox); audit-service consumes it and writes the independent,
hash-chained audit-log entry (CLAUDE.md rule 3 / FR-AUD-01).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import CustodyEvent, EvidenceItem
from app.schemas import CustodyEventCreate, CustodyEventOut
from app.services.custody import ACTION_STATUS, acknowledgement_required, hash_signature

router = APIRouter(prefix="/evidence", tags=["custody"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


async def _require_item(session: AsyncSession, evidence_id: uuid.UUID) -> EvidenceItem:
    item = await session.get(EvidenceItem, evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such evidence item")
    return item


@router.get(
    "/{evidence_id}/custody",
    response_model=list[CustodyEventOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks evidence.vault.read"},
        404: {"description": "No such evidence item"},
    },
)
async def list_custody_events(
    evidence_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("evidence.vault.read")),
) -> list[CustodyEventOut]:
    await _require_item(session, evidence_id)
    rows = (
        await session.scalars(
            select(CustodyEvent)
            .where(CustodyEvent.evidence_id == evidence_id)
            .order_by(CustodyEvent.occurred_at, CustodyEvent.id)
        )
    ).all()
    return [CustodyEventOut.from_model(r) for r in rows]


@router.post(
    "/{evidence_id}/custody",
    response_model=CustodyEventOut,
    status_code=201,
    responses={
        400: {"description": "Acknowledgement required for this action"},
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks evidence.custody.write"},
        404: {"description": "No such evidence item"},
    },
)
async def record_custody_event(
    evidence_id: uuid.UUID,
    payload: CustodyEventCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("evidence.custody.write")),
) -> CustodyEventOut:
    item = await _require_item(session, evidence_id)
    action = payload.action.value

    if acknowledgement_required(action) and not (
        payload.to_officer and payload.acknowledgement_signature
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"action '{action}' requires both to_officer and "
                "acknowledgement_signature (FR-EVID-04)"
            ),
        )

    event = CustodyEvent(
        evidence_id=item.id,
        action=action,
        from_officer=payload.from_officer,
        to_officer=payload.to_officer,
        acknowledgement_signature=(
            hash_signature(payload.acknowledgement_signature)
            if payload.acknowledgement_signature
            else None
        ),
    )
    if payload.occurred_at is not None:
        event.occurred_at = payload.occurred_at
    session.add(event)

    if action in ACTION_STATUS:
        item.status = ACTION_STATUS[action]

    await session.flush()
    await session.refresh(event)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CustodyEventRecorded",
        aggregate_type="custody_event",
        aggregate_id=event.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "custody_event_id": event.id,
            "evidence_id": str(event.evidence_id),
            "action": event.action,
            "from_officer": str(event.from_officer) if event.from_officer else None,
            "to_officer": str(event.to_officer) if event.to_officer else None,
            "acknowledgement": event.acknowledgement_signature is not None,
            "occurred_at": event.occurred_at.isoformat(),
        },
    )
    return CustodyEventOut.from_model(event)
