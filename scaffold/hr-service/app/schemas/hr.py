"""Request/response models for hr-service — matches openapi.yaml exactly.

Field surface mirrors docs Section 9.3.6 (hr_db) column-for-column. The SRS
was corrected (2026-09-05) to add the effective-date/approver/incident-detail
columns FR-HR-03..07 always described; this schema — and migration 0004 —
catches up to that.
"""
import datetime as dt
import decimal
import enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OfficerStatus(str, enum.Enum):
    active = "active"
    on_leave = "on_leave"
    suspended = "suspended"
    retired = "retired"


class ApprovalStatus(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"


class WorkflowStatus(str, enum.Enum):
    """Full transfers/leave_requests status range — for list ?status= filters."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# --- units -------------------------------------------------------------------
class UnitCreate(BaseModel):
    name: str = Field(max_length=100)
    station_id: uuid.UUID


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    station_id: uuid.UUID


# --- officers (FR-HR-01) ------------------------------------------------------
class OfficerCreate(BaseModel):
    user_id: uuid.UUID
    badge_number: str = Field(max_length=20)
    rank: str = Field(max_length=50)
    unit_id: uuid.UUID
    hire_date: dt.date
    supervisor_id: uuid.UUID | None = None
    status: OfficerStatus = OfficerStatus.active


class OfficerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    badge_number: str
    rank: str
    unit_id: uuid.UUID
    hire_date: dt.date
    supervisor_id: uuid.UUID | None = None
    status: OfficerStatus


class OfficerUpdate(BaseModel):
    """Corrections to badge_number/hire_date/status/supervisor_id only.

    rank and unit_id are deliberately NOT editable here — they're owned by the
    audited promotion (FR-HR-04) and transfer-approval (FR-HR-03) workflows,
    so a plain PATCH can't bypass that trail.
    """

    badge_number: str | None = Field(default=None, max_length=20)
    hire_date: dt.date | None = None
    supervisor_id: uuid.UUID | None = None
    status: OfficerStatus | None = None


# --- assignments (FR-HR-02) ---------------------------------------------------
class AssignmentCreate(BaseModel):
    unit_id: uuid.UUID
    start_date: dt.date


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    unit_id: uuid.UUID
    start_date: dt.date
    end_date: dt.date | None = None


# --- transfers (FR-HR-03) -----------------------------------------------------
class TransferCreate(BaseModel):
    to_unit_id: uuid.UUID


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    from_unit_id: uuid.UUID | None = None
    to_unit_id: uuid.UUID | None = None
    status: str
    requested_at: dt.datetime
    effective_date: dt.date | None = None
    approved_by: uuid.UUID | None = None
    created_at: dt.datetime


class TransferStatusUpdate(BaseModel):
    status: ApprovalStatus
    # required when approving; ignored (left NULL) on rejection — docs
    # Section 9.3.6: "set on approval".
    approved_by: uuid.UUID | None = None
    effective_date: dt.date | None = None

    @model_validator(mode="after")
    def _require_fields_on_approval(self) -> "TransferStatusUpdate":
        if self.status == ApprovalStatus.approved and (
            self.approved_by is None or self.effective_date is None
        ):
            raise ValueError("approved_by and effective_date are required when approving")
        return self


# --- promotions (FR-HR-04) ----------------------------------------------------
class PromotionCreate(BaseModel):
    new_rank: str = Field(max_length=50)
    # No separate approval workflow (no status column) — supplied here
    # instead, both required (docs Section 9.3.6, both NOT NULL).
    effective_date: dt.date
    approved_by: uuid.UUID


class PromotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    previous_rank: str
    new_rank: str
    effective_date: dt.date
    approved_by: uuid.UUID
    created_at: dt.datetime


# --- leave requests (FR-HR-05) ------------------------------------------------
class LeaveRequestCreate(BaseModel):
    leave_type: str = Field(max_length=30)
    start_date: dt.date
    end_date: dt.date

    @model_validator(mode="after")
    def _dates_in_order(self) -> "LeaveRequestCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    leave_type: str
    start_date: dt.date
    end_date: dt.date
    status: str
    approved_by: uuid.UUID | None = None
    created_at: dt.datetime


class LeaveStatusUpdate(BaseModel):
    status: ApprovalStatus
    # required when approving; ignored (left NULL) on rejection — docs
    # Section 9.3.6: "set on approval".
    approved_by: uuid.UUID | None = None

    @model_validator(mode="after")
    def _require_approved_by_on_approval(self) -> "LeaveStatusUpdate":
        if self.status == ApprovalStatus.approved and self.approved_by is None:
            raise ValueError("approved_by is required when approving")
        return self


# --- discipline records (FR-HR-06) — confidentiality-gated --------------------
class DisciplineRecordCreate(BaseModel):
    incident_date: dt.date
    description: str
    outcome: str | None = Field(default=None, max_length=100)
    confidentiality_level: str = Field(default="restricted", max_length=20)


class DisciplineRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    incident_date: dt.date
    description: str
    outcome: str | None = None
    confidentiality_level: str
    created_at: dt.datetime


class DisciplineRecordUpdate(BaseModel):
    incident_date: dt.date | None = None
    description: str | None = None
    outcome: str | None = Field(default=None, max_length=100)
    confidentiality_level: str | None = Field(default=None, max_length=20)


# --- performance reviews (FR-HR-07) -------------------------------------------
class PerformanceReviewCreate(BaseModel):
    reviewer_id: uuid.UUID
    period: str = Field(max_length=20)
    # NUMERIC(4,2) tops out at 99.99; no range is specified in docs Section
    # 9.3.6 beyond that, so 0-99.99 is this build's assumption, not the SRS's.
    score: decimal.Decimal = Field(ge=0, le=decimal.Decimal("99.99"), decimal_places=2)
    comments: str | None = None


class PerformanceReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    reviewer_id: uuid.UUID
    period: str
    score: decimal.Decimal
    comments: str | None = None
    created_at: dt.datetime


class PerformanceReviewUpdate(BaseModel):
    period: str | None = Field(default=None, max_length=20)
    score: decimal.Decimal | None = Field(
        default=None, ge=0, le=decimal.Decimal("99.99"), decimal_places=2
    )
    comments: str | None = None
