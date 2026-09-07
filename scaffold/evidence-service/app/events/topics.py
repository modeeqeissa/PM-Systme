"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`)."""
from app.events.config import topic_prefix

_TOPICS = {
    "EvidenceLogged": "evidence.logged",
    "CustodyEventRecorded": "evidence.custody_recorded",
    "EvidenceHashMismatch": "evidence.hash_mismatch",
    # FR-AUD-01: audit access to evidence file content / custody-chain detail,
    # not just writes. EvidenceFileVerified fires on every verify call (the
    # file bytes are read + hashed); a mismatch still additionally emits
    # EvidenceHashMismatch. CustodyChainRead fires on a full chain read.
    "EvidenceFileVerified": "evidence.file_verified",
    "CustodyChainRead": "evidence.custody_chain_read",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
