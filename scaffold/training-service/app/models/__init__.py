"""ORM for training_db (docs Section 9.3.5 / migrations 0001, 0003)."""
from app.models.base import Base
from app.models.training import (
    Assessment,
    AssessmentResult,
    Attendance,
    Certification,
    Course,
    Material,
    OfficerCertification,
    Session,
)

__all__ = [
    "Base",
    "Course",
    "Certification",
    "OfficerCertification",
    "Material",
    "Session",
    "Attendance",
    "Assessment",
    "AssessmentResult",
]
