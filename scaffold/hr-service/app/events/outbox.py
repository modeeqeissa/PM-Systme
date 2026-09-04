"""Enqueue a domain event into the outbox, inside the caller's DB transaction."""
import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.config import SERVICE_NAME
from app.events.models import OutboxEvent
from app.events.topics import topic_for


def build_envelope(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    actor_id,
    actor_role: str | None,
    payload: dict,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_role": actor_role,
        "service": SERVICE_NAME,
        "payload": payload,
    }


def enqueue(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    actor_id=None,
    actor_role: str | None = None,
    payload: dict,
) -> dict:
    """Add an OutboxEvent to ``session`` (committed with the domain write)."""
    envelope = build_envelope(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload=payload,
    )
    session.add(
        OutboxEvent(
            event_id=uuid.UUID(envelope["event_id"]),
            topic=topic_for(event_type),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            body=envelope,
        )
    )
    return envelope
