"""Domain event -> a queued Notification (FR-NOTIF-01), or an OfficerUserMap
update, or nothing.

Every generated notification defaults to channel="in_app" — FR-NOTIF-02
(per-user channel preferences) has no supporting table in SRS §9.3.8, and
notification-service has no access to a recipient's actual email/phone (see
app/services/channels/base.py, TODO.md TD-004), so email/sms aren't a real
option yet regardless of preference.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, OfficerUserMap

log = logging.getLogger("notification-service.mapping")

DEFAULT_CHANNEL = "in_app"

# event_type -> (payload key holding the officer_id, {to_status: template_code})
_OFFICER_EVENT_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "TransferStatusChanged": (
        "officer_id", {"approved": "TRANSFER_APPROVED", "rejected": "TRANSFER_REJECTED"},
    ),
    "LeaveStatusChanged": (
        "officer_id", {"approved": "LEAVE_APPROVED", "rejected": "LEAVE_REJECTED"},
    ),
    "OfficerCertificationStatusChanged": (
        "officer_id", {"expiring_soon": "CERT_EXPIRING", "expired": "CERT_EXPIRED"},
    ),
    "FollowUpActionStatusChanged": (
        "assigned_to", {"overdue": "FOLLOWUP_OVERDUE"},
    ),
}


async def _lookup_user_id(session: AsyncSession, officer_id_str: str) -> uuid.UUID | None:
    try:
        officer_id = uuid.UUID(officer_id_str)
    except (ValueError, TypeError):
        return None
    row = await session.get(OfficerUserMap, officer_id)
    return row.user_id if row else None


def _queue(session: AsyncSession, *, recipient_user_id: uuid.UUID, template_code: str, payload: dict) -> None:
    session.add(
        Notification(
            recipient_user_id=recipient_user_id,
            channel=DEFAULT_CHANNEL,
            template_code=template_code,
            payload=payload,
            status="queued",
        )
    )


async def apply_event(session: AsyncSession, envelope: dict) -> bool:
    """Returns True if a Notification row was queued."""
    event_type = envelope.get("event_type")
    payload = envelope.get("payload") or {}

    if event_type == "OfficerCreated":
        officer_id = payload.get("officer_id")
        user_id = payload.get("user_id")
        if officer_id and user_id:
            key = uuid.UUID(officer_id)
            existing = await session.get(OfficerUserMap, key)
            if existing is None:
                session.add(OfficerUserMap(officer_id=key, user_id=uuid.UUID(user_id)))
            else:
                existing.user_id = uuid.UUID(user_id)
        return False

    if event_type == "AccountLockedOut":
        # identity_db.users.id directly -- no officer_id translation needed.
        user_id = payload.get("user_id")
        if not user_id:
            return False
        _queue(
            session,
            recipient_user_id=uuid.UUID(user_id),
            template_code="ACCOUNT_LOCKED_OUT",
            payload=payload,
        )
        return True

    spec = _OFFICER_EVENT_MAP.get(event_type)
    if spec is None:
        return False
    officer_field, status_templates = spec
    officer_id = payload.get(officer_field)
    template_code = status_templates.get(payload.get("to_status"))
    if officer_id is None or template_code is None:
        return False

    user_id = await _lookup_user_id(session, officer_id)
    if user_id is None:
        # The officer's OfficerCreated event hasn't been consumed yet (or
        # predates this service). Known limitation, not retried — flagged in
        # TODO.md TD-004.
        log.warning(
            "no user_id mapped for officer_id=%s (event_type=%s) — dropping notification",
            officer_id, event_type,
        )
        return False

    _queue(session, recipient_user_id=user_id, template_code=template_code, payload=payload)
    return True
