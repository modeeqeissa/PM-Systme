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
    "evidence.hash_mismatch",
    # FR-DASH-02 mv_unit_readiness (hr-service + training-service)
    "hr.unit_created",
    "hr.officer_created",
    "hr.assignment_recorded",
    "hr.transfer_requested",
    "hr.transfer_status_changed",
    "hr.leave_requested",
    "hr.leave_status_changed",
    "training.officer_certification_issued",
    "training.officer_certification_status_changed",
)


def consumed_topics() -> list[str]:
    prefix = topic_prefix()
    return [f"{prefix}{t}" for t in _BASE_TOPICS]
