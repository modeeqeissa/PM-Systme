import datetime as dt
import uuid
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CertificationStatus(str, Enum):
    active = "active"
    expiring_soon = "expiring_soon"
    expired = "expired"


class AttendanceStatus(str, Enum):
    registered = "registered"
    attended = "attended"
    absent = "absent"


# --- Courses ----------------------------------------------------------------
class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    validity_months: int = Field(gt=0, le=1200)
    mandatory: bool = False


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    validity_months: int | None = Field(default=None, gt=0, le=1200)
    mandatory: bool | None = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    validity_months: int
    mandatory: bool


# --- Certifications (course -> issuable certification) ----------------------
class CertificationCreate(BaseModel):
    course_id: int


class CertificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int


# --- Officer certifications (issuance) ---------------------------------------
class OfficerCertificationCreate(BaseModel):
    officer_id: uuid.UUID
    certification_id: int
    issued_date: dt.date | None = Field(
        default=None,
        description="Defaults to today if omitted. expires_date and status are "
        "always computed server-side, never accepted from the client.",
    )


class OfficerCertificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    officer_id: uuid.UUID
    certification_id: int
    issued_date: dt.date
    expires_date: dt.date
    status: CertificationStatus


class RecomputeResult(BaseModel):
    checked: int
    updated: int


# --- Materials (docs §9.3.5) -----------------------------------------
class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: int
    title: str
    file_ref: str


# --- Sessions (scheduled course instances) --------------------------
class SessionCreate(BaseModel):
    course_id: int
    scheduled_at: dt.datetime
    location: str | None = Field(default=None, max_length=200)
    instructor_officer_id: uuid.UUID | None = None
    capacity: int | None = Field(default=None, gt=0)


class SessionUpdate(BaseModel):
    scheduled_at: dt.datetime | None = None
    location: str | None = Field(default=None, max_length=200)
    instructor_officer_id: uuid.UUID | None = None
    capacity: int | None = Field(default=None, gt=0)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: int
    scheduled_at: dt.datetime
    location: str | None = None
    instructor_officer_id: uuid.UUID | None = None
    capacity: int | None = None


# --- Attendance ---------------------------------------------------
class AttendanceCreate(BaseModel):
    officer_id: uuid.UUID
    status: AttendanceStatus = AttendanceStatus.registered


class AttendanceStatusUpdate(BaseModel):
    status: AttendanceStatus


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    officer_id: uuid.UUID
    status: AttendanceStatus


# --- Assessments + results -------------------------------------
class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    passing_score: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: int
    title: str
    passing_score: Decimal


class AssessmentResultCreate(BaseModel):
    officer_id: uuid.UUID
    score: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class AssessmentResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    officer_id: uuid.UUID
    score: Decimal
    taken_at: dt.datetime
    passed: bool
