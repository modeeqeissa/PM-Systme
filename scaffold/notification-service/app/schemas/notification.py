import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict


class NotificationChannel(str, Enum):
    email = "email"
    sms = "sms"
    push = "push"
    in_app = "in_app"


class NotificationStatus(str, Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_user_id: uuid.UUID
    channel: NotificationChannel
    template_code: str
    payload: dict
    status: NotificationStatus
