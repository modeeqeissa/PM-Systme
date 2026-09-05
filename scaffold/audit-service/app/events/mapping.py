"""Domain event -> audit_logs fields (FR-AUD-01)."""

NIL_UUID = "00000000-0000-0000-0000-000000000000"

# event_type -> (entity_type, action, key in payload holding the entity id)
EVENT_MAP: dict[str, tuple[str, str, str]] = {
    "IncidentReported": ("incident", "create", "incident_id"),
    "CaseOpened": ("case", "create", "case_id"),
    "CaseStatusChanged": ("case", "update", "case_id"),
    "ArrestRecorded": ("arrest", "create", "arrest_id"),
    "StatementRecorded": ("statement", "create", "statement_id"),
    "CourtProceedingRecorded": ("court_proceeding", "create", "court_proceeding_id"),
    "EvidenceLogged": ("evidence_item", "create", "evidence_id"),
    "CustodyEventRecorded": ("custody_event", "create", "custody_event_id"),
    # a verification read that found tampering
    "EvidenceHashMismatch": ("evidence_item", "read", "evidence_id"),
    # iam-service admin / lockout (TD-003). 'delete' = soft-delete/status change
    # per SRS §9.3.10, which is exactly what deactivation is.
    "UserCreated": ("user", "create", "user_id"),
    "UserDeactivated": ("user", "delete", "user_id"),
    "UserRoleReassigned": ("user", "update", "user_id"),
    "AccountLockedOut": ("user", "update", "user_id"),
    # hr-service (FR-HR-01..07)
    "OfficerCreated": ("officer", "create", "officer_id"),
    "OfficerUpdated": ("officer", "update", "officer_id"),
    "UnitCreated": ("unit", "create", "unit_id"),
    "AssignmentRecorded": ("assignment", "create", "assignment_id"),
    "TransferRequested": ("transfer", "create", "transfer_id"),
    "TransferStatusChanged": ("transfer", "update", "transfer_id"),
    "PromotionRecorded": ("promotion", "create", "promotion_id"),
    "LeaveRequested": ("leave_request", "create", "leave_request_id"),
    "LeaveStatusChanged": ("leave_request", "update", "leave_request_id"),
    "DisciplineRecordCreated": ("discipline_record", "create", "discipline_record_id"),
    "DisciplineRecordUpdated": ("discipline_record", "update", "discipline_record_id"),
    "DisciplineRecordDeleted": ("discipline_record", "delete", "discipline_record_id"),
    "PerformanceReviewRecorded": ("performance_review", "create", "performance_review_id"),
    "PerformanceReviewUpdated": ("performance_review", "update", "performance_review_id"),
    "PerformanceReviewDeleted": ("performance_review", "delete", "performance_review_id"),
    # training-service (FR-TRAIN-01..03)
    "CourseCreated": ("course", "create", "course_id"),
    "CourseUpdated": ("course", "update", "course_id"),
    "CourseDeleted": ("course", "delete", "course_id"),
    "CertificationCreated": ("certification", "create", "certification_id"),
    "CertificationDeleted": ("certification", "delete", "certification_id"),
    "OfficerCertificationIssued": ("officer_certification", "create", "officer_certification_id"),
    "OfficerCertificationStatusChanged": (
        "officer_certification", "update", "officer_certification_id",
    ),
}


def to_audit_fields(envelope: dict) -> dict | None:
    """Return audit_logs field values for an event envelope, or None to skip it."""
    mapped = EVENT_MAP.get(envelope.get("event_type"))
    if mapped is None:
        return None
    entity_type, action, id_key = mapped
    payload = envelope.get("payload") or {}
    if id_key not in payload:
        return None
    return {
        "actor_id": envelope.get("actor_id") or NIL_UUID,
        "actor_role": envelope.get("actor_role") or "unknown",
        "service_name": envelope.get("service") or "unknown",
        "entity_type": entity_type,
        "entity_id": str(payload[id_key]),
        "action": action,
        "metadata": {
            "event_id": envelope.get("event_id"),
            "event_type": envelope.get("event_type"),
            "occurred_at": envelope.get("occurred_at"),
            "payload": payload,
        },
    }
