"""Dev channel: the only NotificationChannel implementation until a real
email/SMS/push provider is chosen (TD-004). Logs and keeps an in-memory
record of what would have been sent — an honest stand-in, not a cut corner.
"""
import logging

log = logging.getLogger("notification-service.dev-channel")


class DevChannel:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, *, recipient_user_id, channel: str, rendered_body: str) -> None:
        record = {
            "recipient_user_id": str(recipient_user_id),
            "channel": channel,
            "rendered_body": rendered_body,
        }
        self.sent.append(record)
        log.info("DEV CHANNEL would send [%s] to %s: %s", channel, recipient_user_id, rendered_body)
