"""Domain event names (TD-003) -> Kafka topic names (CLAUDE.md `<entity>.<event>`).

FR-IAM-06 (admin account actions) and FR-IAM-05 (lockout) — audit-service
consumes these into audit_logs.
"""
from app.events.config import topic_prefix

_TOPICS = {
    "UserCreated": "user.created",
    "UserDeactivated": "user.deactivated",
    "UserRoleReassigned": "user.role_reassigned",
    "AccountLockedOut": "account.locked_out",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
