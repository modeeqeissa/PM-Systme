"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`)."""
from app.events.config import topic_prefix

# event_type (PascalCase, carried in the envelope) -> base topic
_TOPICS = {
    "IncidentReported": "incident.reported",
    "CaseOpened": "case.opened",
    "CaseStatusChanged": "case.status_changed",
    "ArrestRecorded": "case.arrest_recorded",
    "StatementRecorded": "case.statement_recorded",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
