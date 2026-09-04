"""ORM for hr_db (docs Section 9.3.6 / migration 0001). Outbox model lives in
app.events.models (migration 0002), imported separately where needed."""
from app.models.base import Base
from app.models.hr import (
    Assignment,
    DisciplineRecord,
    LeaveRequest,
    Officer,
    PerformanceReview,
    Promotion,
    Transfer,
    Unit,
)

__all__ = [
    "Base",
    "Unit",
    "Officer",
    "Assignment",
    "Transfer",
    "Promotion",
    "LeaveRequest",
    "DisciplineRecord",
    "PerformanceReview",
]
