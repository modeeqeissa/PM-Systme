"""Domain event -> a queued Notification (FR-NOTIF-01), OfficerUserMap
maintenance, or nothing.

Every generated notification currently uses channel="in_app" — the DevChannel
is the only real delivery path (TODO.md TD-004), and notification-service has
no access to a recipient's email/phone anyway. Per-user opt-out per channel
(FR-NOTIF-02) is honoured at delivery time (app/services/delivery.py), not
here.
"""
import logging
import uuid

from sqlalchemy import update
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


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _officer_row(session: AsyncSession, officer_id_str) -> OfficerUserMap | None:
    key = _as_uuid(officer_id_str)
    return await session.get(OfficerUserMap, key) if key else None


def _queue(
    session: AsyncSession, *, recipient_user_id: uuid.UUID, template_code: str, payload: dict
) -> None:
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
    """Returns True if at least one Notification row was queued."""
    event_type = envelope.get("event_type")
    payload = envelope.get("payload") or {}

    if event_type == "OfficerCreated":
        officer_id = _as_uuid(payload.get("officer_id"))
        user_id = _as_uuid(payload.get("user_id"))
        if officer_id and user_id:
            supervisor = _as_uuid(payload.get("supervisor_id"))
            existing = await session.get(OfficerUserMap, officer_id)
            if existing is None:
                session.add(
                    OfficerUserMap(
                        officer_id=officer_id,
                        user_id=user_id,
                        supervisor_officer_id=supervisor,
                    )
                )
            else:
                existing.user_id = user_id
                existing.supervisor_officer_id = supervisor
        return False

    if event_type == "OfficerSupervisorChanged":
        officer_id = _as_uuid(payload.get("officer_id"))
        if officer_id is None:
            return False
        result = await session.execute(
            update(OfficerUserMap)
            .where(OfficerUserMap.officer_id == officer_id)
            .values(supervisor_officer_id=_as_uuid(payload.get("supervisor_id")))
        )
        if result.rowcount == 0:
            # OfficerCreated for this officer not consumed yet — cross-topic
            # ordering, same caveat as TODO.md TD-004.
            log.warning(
                "OfficerSupervisorChanged for unmapped officer_id=%s — skipped", officer_id
            )
        return False

    if event_type == "AccountLockedOut":
        # identity_db.users.id directly -- no officer_id translation needed.
        user_id = _as_uuid(payload.get("user_id"))
        if user_id is None:
            return False
        _queue(session, recipient_user_id=user_id, template_code="ACCOUNT_LOCKED_OUT", payload=payload)
        return True

    if event_type == "CaseOfficerAssigned":
        # FR-CASE-07 — notify the officer added to (or re-roled on) a case.
        # payload.officer_id is an hr_db.officers.id, resolved via the map.
        row = await _officer_row(session, payload.get("officer_id"))
        if row is None:
            log.warning(
                "no user_id mapped for officer_id=%s (CaseOfficerAssigned) — dropping notification",
                payload.get("officer_id"),
            )
            return False
        _queue(
            session,
            recipient_user_id=row.user_id,
            template_code="CASE_OFFICER_ASSIGNED",
            payload=payload,
        )
        return True

    spec = _OFFICER_EVENT_MAP.get(event_type)
    if spec is None:
        return False
    officer_field, status_templates = spec
    template_code = status_templates.get(payload.get("to_status"))
    if payload.get(officer_field) is None or template_code is None:
        return False

    row = await _officer_row(session, payload[officer_field])
    if row is None:
        log.warning(
            "no user_id mapped for officer_id=%s (event_type=%s) — dropping notification",
            payload[officer_field], event_type,
        )
        return False

    queued_any = False
    _queue(session, recipient_user_id=row.user_id, template_code=template_code, payload=payload)
    queued_any = True

    # FR-COMM-04: an overdue follow-up also notifies the assignee's supervisor.
    if event_type == "FollowUpActionStatusChanged" and row.supervisor_officer_id is not None:
        sup = await session.get(OfficerUserMap, row.supervisor_officer_id)
        if sup is not None:
            _queue(
                session,
                recipient_user_id=sup.user_id,
                template_code="FOLLOWUP_OVERDUE_SUPERVISOR",
                payload=payload,
            )
        else:
            log.warning(
                "supervisor officer_id=%s not mapped — supervisor notification skipped",
                row.supervisor_officer_id,
            )

    return queued_any
