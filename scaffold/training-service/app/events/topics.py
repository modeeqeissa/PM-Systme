"""Domain event names (SRS §3.4) -> Kafka topic names (CLAUDE.md `<entity>.<event>`).

Every mutating training endpoint enqueues one of these (CLAUDE.md rule 3).
OfficerCertificationStatusChanged follows the same single *StatusChanged event
per resource convention as hr-service's TransferStatusChanged/LeaveStatusChanged
(payload carries from_status/to_status) rather than a separate event per outcome
(e.g. distinct CertificationExpiring/CertificationExpired events) — one topic to
consume, whether the transition is issue-time, on-demand recompute, or the
periodic background sweep (FR-TRAIN-03).
"""
from app.events.config import topic_prefix

# event_type (PascalCase, carried in the envelope) -> base topic
_TOPICS = {
    "CourseCreated": "training.course_created",
    "CourseUpdated": "training.course_updated",
    "CourseDeleted": "training.course_deleted",
    "CertificationCreated": "training.certification_created",
    "CertificationDeleted": "training.certification_deleted",
    "OfficerCertificationIssued": "training.officer_certification_issued",
    "OfficerCertificationStatusChanged": "training.officer_certification_status_changed",
    "MaterialAdded": "training.material_added",
    "MaterialRemoved": "training.material_removed",
    "SessionScheduled": "training.session_scheduled",
    "SessionUpdated": "training.session_updated",
    "AttendanceRecorded": "training.attendance_recorded",
    "AttendanceStatusChanged": "training.attendance_status_changed",
    "AssessmentCreated": "training.assessment_created",
    "AssessmentResultRecorded": "training.assessment_result_recorded",
}

ALL_TOPICS = tuple(_TOPICS.values())


def topic_for(event_type: str) -> str:
    try:
        base = _TOPICS[event_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown event_type {event_type!r}") from exc
    return f"{topic_prefix()}{base}"
