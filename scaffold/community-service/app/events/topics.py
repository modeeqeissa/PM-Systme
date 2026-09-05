"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`).

Every mutating community endpoint enqueues one of these (CLAUDE.md rule 3).
FollowUpActionStatusChanged covers both the manual pending->completed
transition and the automatic pending->overdue transition (FR-COMM-04) —
notification-service listens for a to_status of "overdue" to notify the
assigned officer.
"""
from app.events.config import topic_prefix

# event_type (PascalCase, carried in the envelope) -> base topic
_TOPICS = {
    "MeetingLogged": "community.meeting_logged",
    "ConcernLogged": "community.concern_logged",
    "ConcernStatusChanged": "community.concern_status_changed",
    "FollowUpActionCreated": "community.follow_up_action_created",
    "FollowUpActionStatusChanged": "community.follow_up_action_status_changed",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
