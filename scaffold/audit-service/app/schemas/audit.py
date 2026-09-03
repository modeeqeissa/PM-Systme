import datetime as dt
import enum
import uuid

from pydantic import BaseModel


class AuditAction(str, enum.Enum):
    create = "create"
    read = "read"
    update = "update"
    delete = "delete"
    export = "export"


class AuditEntry(BaseModel):
    """Response item for GET /audit — matches openapi.yaml AuditEntry."""

    id: int
    actor_id: uuid.UUID
    actor_role: str
    service_name: str
    entity_type: str
    entity_id: str
    action: AuditAction
    timestamp: dt.datetime
    prev_hash: str
    record_hash: str
    metadata: dict | None = None

    @classmethod
    def from_model(cls, row) -> "AuditEntry":
        return cls(
            id=row.id,
            actor_id=row.actor_id,
            actor_role=row.actor_role,
            service_name=row.service_name,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            action=row.action,
            timestamp=row.timestamp,
            prev_hash=row.prev_hash,
            record_hash=row.record_hash,
            metadata=row.metadata_,
        )


class ChainVerification(BaseModel):
    entries_checked: int
    valid: bool
    broken_at: int | None = None
