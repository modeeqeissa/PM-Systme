import datetime as dt
import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CertificationStatus(str, Enum):
    active = "active"
    expiring_soon = "expiring_soon"
    expired = "expired"


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
