import datetime as dt
import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ConcernStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class FollowUpActionStatus(str, Enum):
    pending = "pending"
    overdue = "overdue"
    completed = "completed"


class DecisionStatus(str, Enum):
    pending = "pending"
    implemented = "implemented"
    abandoned = "abandoned"


# --- Communities ------------------------------------------------------------
class CommunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    station_id: uuid.UUID
    description: str | None = None


class CommunityUpdate(BaseModel):
    """Partial update — `station_id` is the ownership anchor and is not editable."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None


class CommunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    station_id: uuid.UUID
    description: str | None = None


# --- Organizations --------------------------------------------------------
class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    community_id: uuid.UUID | None = None
    contact_name: str | None = Field(default=None, max_length=150)
    contact_phone: str | None = Field(default=None, max_length=30)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    community_id: uuid.UUID | None = None
    contact_name: str | None = Field(default=None, max_length=150)
    contact_phone: str | None = Field(default=None, max_length=30)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    community_id: uuid.UUID | None = None
    contact_name: str | None = None
    contact_phone: str | None = None


# --- Meetings -----------------------------------------------------------------
class MeetingCreate(BaseModel):
    station_id: uuid.UUID
    community_id: uuid.UUID | None = None
    facilitator_id: uuid.UUID
    meeting_date: dt.date
    location: str
    attendee_summary: str | None = None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    station_id: uuid.UUID
    community_id: uuid.UUID | None = None
    facilitator_id: uuid.UUID
    meeting_date: dt.date
    location: str
    attendee_summary: str | None = None


# --- Meeting minutes -----------------------------------------------------
class MeetingMinutesCreate(BaseModel):
    content: str = Field(min_length=1)
    recorded_by: uuid.UUID


class MeetingMinutesUpdate(BaseModel):
    content: str = Field(min_length=1)


class MeetingMinutesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID
    content: str
    recorded_by: uuid.UUID


# --- Decisions ---------------------------------------------------------
class DecisionCreate(BaseModel):
    description: str = Field(min_length=1)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID
    description: str
    status: DecisionStatus


class DecisionStatusUpdate(BaseModel):
    status: DecisionStatus


# --- Concerns -------------------------------------------------------------
class ConcernCreate(BaseModel):
    meeting_id: uuid.UUID | None = None
    category: str
    description: str = Field(min_length=1)
    raised_by: str | None = Field(default=None, max_length=150)


class ConcernOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID | None
    category: str
    description: str
    raised_by: str | None
    status: ConcernStatus


class ConcernStatusUpdate(BaseModel):
    status: ConcernStatus


# --- Follow-up actions ------------------------------------------------------
class FollowUpActionCreate(BaseModel):
    description: str = Field(min_length=1)
    assigned_to: uuid.UUID
    due_date: dt.date


class FollowUpActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    concern_id: uuid.UUID
    description: str
    assigned_to: uuid.UUID
    due_date: dt.date
    status: FollowUpActionStatus


class FollowUpActionStatusUpdate(BaseModel):
    status: FollowUpActionStatus


class RecomputeResult(BaseModel):
    checked: int
    updated: int
