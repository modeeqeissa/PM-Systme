"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`)."""
from app.events.config import topic_prefix

_TOPICS = {
    "EvidenceLogged": "evidence.logged",
    "CustodyEventRecorded": "evidence.custody_recorded",
    "EvidenceHashMismatch": "evidence.hash_mismatch",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
