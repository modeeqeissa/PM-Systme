"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`).

FR-INT-05 requires every integration call to be authenticated, scoped AND
logged — external_system_logs (this service's own table) is the operational
record, but audit-service's independent, hash-chained audit_logs is the
tamper-evident one (FR-AUD-01/SRS §5.8), so every mutating endpoint here
also enqueues one of these (CLAUDE.md rule 3).
"""
from app.events.config import topic_prefix

_TOPICS = {
    "IntegrationConfigUpdated": "integration.config_updated",
    "ExternalSystemCallLogged": "integration.external_system_call_logged",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
