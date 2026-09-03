"""Tamper-evident hash chain over audit_logs (FR-AUD-02).

record_hash = SHA-256( prev_hash ‖ canonical(entry fields) )

The first entry chains from GENESIS (64 zeros). Writers serialise on a
transaction-scoped advisory lock so concurrent inserts cannot fork the chain
(the single consumer already serialises in practice; the lock is belt-and-braces).
"""
import datetime as dt
import hashlib
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

GENESIS = "0" * 64
_CHAIN_LOCK_KEY = 0x4155_4449_5401  # "AUDIT" + 1


def _canonical(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)


def compute_record_hash(prev_hash: str, entry: dict) -> str:
    payload = {
        "actor_id": str(entry["actor_id"]),
        "actor_role": entry["actor_role"],
        "service_name": entry["service_name"],
        "entity_type": entry["entity_type"],
        "entity_id": entry["entity_id"],
        "action": entry["action"],
        "timestamp": entry["timestamp"].isoformat()
        if isinstance(entry["timestamp"], dt.datetime)
        else entry["timestamp"],
        "metadata": entry.get("metadata"),
    }
    return hashlib.sha256((prev_hash + _canonical(payload)).encode()).hexdigest()


async def append_entry(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | str,
    actor_role: str,
    service_name: str,
    entity_type: str,
    entity_id: str,
    action: str,
    metadata: dict | None = None,
) -> AuditLog:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})

    prev_hash = (
        await session.scalar(
            select(AuditLog.record_hash).order_by(AuditLog.id.desc()).limit(1)
        )
    ) or GENESIS

    timestamp = dt.datetime.now(dt.timezone.utc)
    entry = {
        "actor_id": actor_id,
        "actor_role": actor_role,
        "service_name": service_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "timestamp": timestamp,
        "metadata": metadata,
    }
    record_hash = compute_record_hash(prev_hash, entry)

    row = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        service_name=service_name,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        timestamp=timestamp,
        prev_hash=prev_hash,
        record_hash=record_hash,
        metadata_=metadata,
    )
    session.add(row)
    await session.flush()
    return row


async def verify_chain(session: AsyncSession) -> tuple[int, bool, int | None]:
    rows = (await session.scalars(select(AuditLog).order_by(AuditLog.id))).all()
    expected_prev = GENESIS
    for row in rows:
        if row.prev_hash != expected_prev:
            return len(rows), False, row.id
        recomputed = compute_record_hash(
            row.prev_hash,
            {
                "actor_id": row.actor_id,
                "actor_role": row.actor_role,
                "service_name": row.service_name,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "action": row.action,
                "timestamp": row.timestamp,
                "metadata": row.metadata_,
            },
        )
        if recomputed != row.record_hash:
            return len(rows), False, row.id
        expected_prev = row.record_hash
    return len(rows), True, None
