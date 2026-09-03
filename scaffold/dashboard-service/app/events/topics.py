"""Topics audit-service consumes (must match the producers' base names)."""
from app.config import topic_prefix

# base topic -> nothing; we just need the set. Kept aligned with
# case-service/app/events/topics.py and evidence-service/app/events/topics.py.
_BASE_TOPICS = (
    "case.opened",
    "case.status_changed",
    "case.arrest_recorded",
    "evidence.logged",
    "evidence.custody_recorded",
)


def consumed_topics() -> list[str]:
    prefix = topic_prefix()
    return [f"{prefix}{t}" for t in _BASE_TOPICS]
