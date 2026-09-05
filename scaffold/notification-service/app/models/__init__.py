"""ORM for notification_db (docs Section 9.3.8 / migration 0001+0002)."""
from app.models.base import Base
from app.models.notification import (
    ConsumedEvent,
    Notification,
    NotificationPreference,
    NotificationTemplate,
    OfficerUserMap,
)

__all__ = [
    "Base",
    "NotificationTemplate",
    "Notification",
    "NotificationPreference",
    "OfficerUserMap",
    "ConsumedEvent",
]
