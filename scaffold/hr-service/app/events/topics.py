"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`).

Every mutating HR endpoint enqueues one of these (CLAUDE.md rule 3: every write
to HR/discipline data must emit an audit event). Approve/reject workflows use a
single *StatusChanged event per resource (payload carries from_status/to_status),
mirroring case-service's CaseStatusChanged rather than one event per outcome.
"""
from app.events.config import topic_prefix

# event_type (PascalCase, carried in the envelope) -> base topic
_TOPICS = {
    "OfficerCreated": "hr.officer_created",
    "OfficerUpdated": "hr.officer_updated",
    "OfficerSupervisorChanged": "hr.officer_supervisor_changed",
    "UnitCreated": "hr.unit_created",
    "AssignmentRecorded": "hr.assignment_recorded",
    "TransferRequested": "hr.transfer_requested",
    "TransferStatusChanged": "hr.transfer_status_changed",
    "PromotionRecorded": "hr.promotion_recorded",
    "LeaveRequested": "hr.leave_requested",
    "LeaveStatusChanged": "hr.leave_status_changed",
    "DisciplineRecordCreated": "hr.discipline_record_created",
    "DisciplineRecordUpdated": "hr.discipline_record_updated",
    "DisciplineRecordDeleted": "hr.discipline_record_deleted",
    "PerformanceReviewRecorded": "hr.performance_review_recorded",
    "PerformanceReviewUpdated": "hr.performance_review_updated",
    "PerformanceReviewDeleted": "hr.performance_review_deleted",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
