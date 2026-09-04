"""Topics audit-service consumes (must match the producers' base names)."""
from app.config import topic_prefix

# base topic -> nothing; we just need the set. Kept aligned with the producers'
# app/events/topics.py (case-service, evidence-service, iam-service).
_BASE_TOPICS = (
    "incident.reported",
    "case.opened",
    "case.status_changed",
    "case.arrest_recorded",
    "case.statement_recorded",
    "case.court_proceeding_recorded",
    "evidence.logged",
    "evidence.custody_recorded",
    "evidence.hash_mismatch",
    # iam-service admin / lockout events (TD-003, FR-IAM-05/06)
    "user.created",
    "user.deactivated",
    "user.role_reassigned",
    "account.locked_out",
)


def consumed_topics() -> list[str]:
    prefix = topic_prefix()
    return [f"{prefix}{t}" for t in _BASE_TOPICS]
