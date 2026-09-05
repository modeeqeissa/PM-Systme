"""Pluggable delivery channel interface (FR-NOTIF-01, TD-004).

No real email/SMS/push provider is chosen yet, and — separately —
notification-service has no access to a recipient's actual email address or
phone number (that lives in identity_db, and CLAUDE.md rule 1 forbids
reading another service's database directly). A real provider integration
will need both a chosen vendor AND a way to resolve contact details, neither
of which exists today; see TODO.md TD-004. Every channel used until then is
DevChannel, regardless of the notification's `channel` column value.
"""
from typing import Protocol


class DeliveryError(Exception):
    """Raised by a channel implementation when a send attempt fails."""


class NotificationChannel(Protocol):
    async def send(
        self, *, recipient_user_id, channel: str, subject: str | None, rendered_body: str
    ) -> None:
        """Attempt delivery. Raise DeliveryError on failure."""
        ...
