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
    "case.officer_assigned",
    "case.officer_unassigned",
    "evidence.logged",
    "evidence.custody_recorded",
    "evidence.hash_mismatch",
    # iam-service admin / lockout events (TD-003, FR-IAM-05/06)
    "user.created",
    "user.deactivated",
    "user.role_reassigned",
    "account.locked_out",
    # hr-service (FR-HR-01..07)
    "hr.officer_created",
    "hr.officer_updated",
    "hr.officer_supervisor_changed",
    "hr.unit_created",
    "hr.assignment_recorded",
    "hr.transfer_requested",
    "hr.transfer_status_changed",
    "hr.promotion_recorded",
    "hr.leave_requested",
    "hr.leave_status_changed",
    "hr.discipline_record_created",
    "hr.discipline_record_updated",
    "hr.discipline_record_deleted",
    "hr.performance_review_recorded",
    "hr.performance_review_updated",
    "hr.performance_review_deleted",
    # training-service (FR-TRAIN-01..03)
    "training.course_created",
    "training.course_updated",
    "training.course_deleted",
    "training.certification_created",
    "training.certification_deleted",
    "training.officer_certification_issued",
    "training.officer_certification_status_changed",
    # community-service (FR-COMM-01..04)
    "community.meeting_logged",
    "community.concern_logged",
    "community.concern_status_changed",
    "community.follow_up_action_created",
    "community.follow_up_action_status_changed",
    # integration-gateway-service (FR-INT-01..05)
    "integration.config_updated",
    "integration.external_system_call_logged",
)


def consumed_topics() -> list[str]:
    prefix = topic_prefix()
    return [f"{prefix}{t}" for t in _BASE_TOPICS]
