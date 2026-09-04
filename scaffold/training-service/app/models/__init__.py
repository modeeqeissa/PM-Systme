"""ORM for training_db (docs Section 9.3.5 / migration 0001). Phase 1 stub."""
from app.models.base import Base
from app.models.training import Certification, Course, OfficerCertification

__all__ = ["Base", "Course", "Certification", "OfficerCertification"]
