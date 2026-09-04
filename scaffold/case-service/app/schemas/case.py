import datetime as dt
import enum
import uuid

from pydantic import BaseModel, ConfigDict


class CaseStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    referred_prosecution = "referred_prosecution"
    closed = "closed"
    suspended = "suspended"


class CaseOut(BaseModel):
    """Response body for GET /cases/{case_id} — matches openapi.yaml Case."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_number: str
    incident_id: uuid.UUID | None = None
    status: CaseStatus
    lead_officer_id: uuid.UUID
    opened_at: dt.datetime
    closed_at: dt.datetime | None = None


class CaseStatusUpdate(BaseModel):
    """Request body for PATCH /cases/{case_id}/status."""

    status: CaseStatus


class CaseCreate(BaseModel):
    """Request body for POST /cases — escalate an incident into a formal case (FR-CASE-02)."""

    incident_id: uuid.UUID | None = None
    lead_officer_id: uuid.UUID


class ArrestCreate(BaseModel):
    """Request body for POST /cases/{case_id}/arrests."""

    officer_id: uuid.UUID
    suspect_id: uuid.UUID
    arrest_date: dt.datetime
    location: str | None = None
    legal_basis: str | None = None


class ArrestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    officer_id: uuid.UUID
    suspect_id: uuid.UUID
    arrest_date: dt.datetime
    location: str | None = None
    legal_basis: str | None = None


class PartyType(str, enum.Enum):
    witness = "witness"
    suspect = "suspect"
    victim = "victim"


class StatementCreate(BaseModel):
    """Request body for POST /cases/{case_id}/statements."""

    recorded_by: uuid.UUID
    party_type: PartyType
    statement_text: str


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    recorded_by: uuid.UUID
    party_type: PartyType
    statement_text: str
    recorded_at: dt.datetime
