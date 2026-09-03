import datetime as dt
import enum
import uuid

from pydantic import BaseModel, ConfigDict


class ItemStatus(str, enum.Enum):
    logged = "logged"
    in_analysis = "in_analysis"
    in_court = "in_court"
    disposed = "disposed"


class EvidenceItemOut(BaseModel):
    """Response body — matches openapi.yaml EvidenceItem."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    item_type: str
    description: str
    collected_by: uuid.UUID
    collected_at: dt.datetime
    storage_ref: str | None = None
    sha256_hash: str | None = None
    status: ItemStatus


class HashVerification(BaseModel):
    """Response body for POST /evidence/{id}/verify — matches openapi.yaml."""

    evidence_id: uuid.UUID
    stored_hash: str
    computed_hash: str
    match: bool
    verified_at: dt.datetime
