import datetime as dt
import enum
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PersonCreate(BaseModel):
    """Request body for POST /persons (docs §9.3.2)."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: dt.date | None = None
    national_id: str | None = Field(default=None, max_length=50)
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None


class PersonUpdate(BaseModel):
    """Request body for PATCH /persons/{id} — every field optional.

    Only keys actually present in the request are applied (partial update);
    `first_name` / `last_name` cannot be blanked (min_length=1).
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: dt.date | None = None
    national_id: str | None = Field(default=None, max_length=50)
    gender: str | None = Field(default=None, max_length=20)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: dt.date | None = None
    national_id: str | None = None
    gender: str | None = None
    address: str | None = None
    phone: str | None = None
    notes: str | None = None
    created_at: dt.datetime


class CasePersonRole(str, enum.Enum):
    suspect = "suspect"
    victim = "victim"
    witness = "witness"


class CasePersonCreate(BaseModel):
    """Request body for POST /cases/{case_id}/persons — link an existing person."""

    person_id: uuid.UUID
    role: CasePersonRole


class CasePersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    person_id: uuid.UUID
    role: CasePersonRole
