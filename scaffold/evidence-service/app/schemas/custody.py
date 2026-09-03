import datetime as dt
import enum
import uuid

from pydantic import BaseModel


class CustodyAction(str, enum.Enum):
    collected = "collected"
    transferred = "transferred"
    analyzed = "analyzed"
    stored = "stored"
    submitted_court = "submitted_court"
    disposed = "disposed"


class CustodyEventCreate(BaseModel):
    action: CustodyAction
    from_officer: uuid.UUID | None = None
    to_officer: uuid.UUID | None = None
    acknowledgement_signature: str | None = None
    occurred_at: dt.datetime | None = None


class CustodyEventOut(BaseModel):
    """Response body — matches openapi.yaml CustodyEvent.

    The raw acknowledgement signature/PIN is never returned; only whether one was
    recorded (``acknowledgement``).
    """

    id: int
    evidence_id: uuid.UUID
    action: CustodyAction
    from_officer: uuid.UUID | None = None
    to_officer: uuid.UUID | None = None
    acknowledgement: bool
    occurred_at: dt.datetime

    @classmethod
    def from_model(cls, event) -> "CustodyEventOut":
        return cls(
            id=event.id,
            evidence_id=event.evidence_id,
            action=event.action,
            from_officer=event.from_officer,
            to_officer=event.to_officer,
            acknowledgement=event.acknowledgement_signature is not None,
            occurred_at=event.occurred_at,
        )
