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


# --- Meetings -----------------------------------------------------------------
class MeetingCreate(BaseModel):
    station_id: uuid.UUID
    facilitator_id: uuid.UUID
    meeting_date: dt.date
    location: str
    attendee_summary: str | None = None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    station_id: uuid.UUID
    facilitator_id: uuid.UUID
    meeting_date: dt.date
    location: str
    attendee_summary: str | None = None


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
