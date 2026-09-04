"""ORM for notification_db (docs Section 9.3.8 / migration 0001). Phase 1 stub."""
from app.models.base import Base
from app.models.notification import Notification, NotificationTemplate

__all__ = ["Base", "NotificationTemplate", "Notification"]
