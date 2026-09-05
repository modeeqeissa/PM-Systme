"""Kafka -> audit_logs: mapping, idempotency, hash chain (FR-AUD-01/02, SRS §9.4)."""
import uuid

from sqlalchemy import select

from app.models import AuditLog, ConsumedEvent
from app.services.hashchain import GENESIS, verify_chain
from tests.conftest import OwnerSession


async def _audit_rows() -> list[AuditLog]:
    async with OwnerSession() as s:
        return list((await s.scalars(select(AuditLog).order_by(AuditLog.id))).all())


async def test_case_opened_becomes_a_create_audit_entry(client, emit, consumer):
    case_id = str(uuid.uuid4())
    env = await emit(
        "CaseOpened",
        {"case_id": case_id, "case_number": "CASE-2026-000001"},
        actor_id=str(uuid.uuid4()),
        actor_role="Investigator",
        service="case-service",
    )
    assert await consumer.process_available() == 1

    rows = await _audit_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "case" and row.entity_id == case_id
    assert row.action == "create"
    assert str(row.actor_id) == env["actor_id"]
    assert row.actor_role == "Investigator"
    assert row.service_name == "case-service"
    assert row.metadata_["event_id"] == env["event_id"]
    assert row.metadata_["payload"]["case_number"] == "CASE-2026-000001"
    assert row.prev_hash == GENESIS


async def test_all_event_types_map_to_expected_entity_and_action(client, emit, consumer):
    await emit("CaseOpened", {"case_id": str(uuid.uuid4())})
    await emit("CaseStatusChanged", {"case_id": str(uuid.uuid4()), "to_status": "closed"})
    await emit("ArrestRecorded", {"arrest_id": str(uuid.uuid4())})
    await emit("StatementRecorded", {"statement_id": str(uuid.uuid4())})
    await emit("CourtProceedingRecorded", {"court_proceeding_id": str(uuid.uuid4())})
    await emit("EvidenceLogged", {"evidence_id": str(uuid.uuid4())}, service="evidence-service")
    await emit("CustodyEventRecorded", {"custody_event_id": 7}, service="evidence-service")
    await emit(
        "EvidenceHashMismatch",
        {"evidence_id": str(uuid.uuid4()), "stored_hash": "a" * 64, "computed_hash": "b" * 64},
        service="evidence-service",
    )

    # iam-service admin / lockout events (TD-003)
    await emit("UserCreated", {"user_id": str(uuid.uuid4())}, service="iam-service")
    await emit("UserDeactivated", {"user_id": str(uuid.uuid4())}, service="iam-service")
    await emit("UserRoleReassigned", {"user_id": str(uuid.uuid4())}, service="iam-service")
    await emit(
        "AccountLockedOut",
        {"user_id": str(uuid.uuid4()), "failed_login_count": 5},
        service="iam-service", actor_role="system",
    )

    # hr-service (FR-HR-01..07)
    await emit("OfficerCreated", {"officer_id": str(uuid.uuid4())}, service="hr-service")
    await emit("OfficerUpdated", {"officer_id": str(uuid.uuid4())}, service="hr-service")
    await emit("UnitCreated", {"unit_id": str(uuid.uuid4())}, service="hr-service")
    await emit("AssignmentRecorded", {"assignment_id": str(uuid.uuid4())}, service="hr-service")
    await emit("TransferRequested", {"transfer_id": str(uuid.uuid4())}, service="hr-service")
    await emit("TransferStatusChanged", {"transfer_id": str(uuid.uuid4())}, service="hr-service")
    await emit("PromotionRecorded", {"promotion_id": str(uuid.uuid4())}, service="hr-service")
    await emit("LeaveRequested", {"leave_request_id": str(uuid.uuid4())}, service="hr-service")
    await emit("LeaveStatusChanged", {"leave_request_id": str(uuid.uuid4())}, service="hr-service")
    await emit(
        "DisciplineRecordCreated", {"discipline_record_id": str(uuid.uuid4())}, service="hr-service"
    )
    await emit(
        "DisciplineRecordUpdated", {"discipline_record_id": str(uuid.uuid4())}, service="hr-service"
    )
    await emit(
        "DisciplineRecordDeleted", {"discipline_record_id": str(uuid.uuid4())}, service="hr-service"
    )
    await emit(
        "PerformanceReviewRecorded",
        {"performance_review_id": str(uuid.uuid4())},
        service="hr-service",
    )
    await emit(
        "PerformanceReviewUpdated",
        {"performance_review_id": str(uuid.uuid4())},
        service="hr-service",
    )
    await emit(
        "PerformanceReviewDeleted",
        {"performance_review_id": str(uuid.uuid4())},
        service="hr-service",
    )

    # training-service (FR-TRAIN-01..03)
    await emit("CourseCreated", {"course_id": 1}, service="training-service")
    await emit("CourseUpdated", {"course_id": 1}, service="training-service")
    await emit("CourseDeleted", {"course_id": 1}, service="training-service")
    await emit("CertificationCreated", {"certification_id": 1}, service="training-service")
    await emit("CertificationDeleted", {"certification_id": 1}, service="training-service")
    await emit(
        "OfficerCertificationIssued",
        {"officer_certification_id": str(uuid.uuid4())},
        service="training-service",
    )
    await emit(
        "OfficerCertificationStatusChanged",
        {"officer_certification_id": str(uuid.uuid4())},
        service="training-service",
    )

    # community-service (FR-COMM-01..04)
    await emit("MeetingLogged", {"meeting_id": str(uuid.uuid4())}, service="community-service")
    await emit("ConcernLogged", {"concern_id": str(uuid.uuid4())}, service="community-service")
    await emit(
        "ConcernStatusChanged", {"concern_id": str(uuid.uuid4())}, service="community-service"
    )
    await emit(
        "FollowUpActionCreated",
        {"follow_up_action_id": str(uuid.uuid4())},
        service="community-service",
    )
    await emit(
        "FollowUpActionStatusChanged",
        {"follow_up_action_id": str(uuid.uuid4())},
        service="community-service",
    )

    # integration-gateway-service (FR-INT-01..05)
    await emit(
        "IntegrationConfigUpdated",
        {"integration_config_id": 1},
        service="integration-gateway-service",
    )
    await emit(
        "ExternalSystemCallLogged",
        {"correlation_id": str(uuid.uuid4())},
        service="integration-gateway-service",
    )

    assert await consumer.process_available() == 41
    rows = await _audit_rows()
    seen = {(r.entity_type, r.action) for r in rows}
    assert seen == {
        ("case", "create"),
        ("case", "update"),
        ("arrest", "create"),
        ("statement", "create"),
        ("court_proceeding", "create"),
        ("evidence_item", "create"),
        ("custody_event", "create"),
        ("evidence_item", "read"),   # hash-mismatch detection
        ("user", "create"),          # UserCreated
        ("user", "delete"),          # UserDeactivated (soft-delete/status change)
        ("user", "update"),          # UserRoleReassigned + AccountLockedOut
        ("officer", "create"),
        ("officer", "update"),
        ("unit", "create"),
        ("assignment", "create"),
        ("transfer", "create"),
        ("transfer", "update"),
        ("promotion", "create"),
        ("leave_request", "create"),
        ("leave_request", "update"),
        ("discipline_record", "create"),
        ("discipline_record", "update"),
        ("discipline_record", "delete"),
        ("performance_review", "create"),
        ("performance_review", "update"),
        ("performance_review", "delete"),
        ("course", "create"),
        ("course", "update"),
        ("course", "delete"),
        ("certification", "create"),
        ("certification", "delete"),
        ("officer_certification", "create"),
        ("officer_certification", "update"),
        ("meeting", "create"),
        ("concern", "create"),
        ("concern", "update"),
        ("follow_up_action", "create"),
        ("follow_up_action", "update"),
        ("integration_config", "update"),
        ("external_system_call", "create"),
    }
    # custody event id was an int in the payload -> stored as text entity_id
    custody = next(r for r in rows if r.entity_type == "custody_event")
    assert custody.entity_id == "7"
    lockout = next(
        r for r in rows
        if r.metadata_.get("event_type") == "AccountLockedOut"
    )
    assert lockout.entity_type == "user" and lockout.action == "update"
    assert lockout.actor_role == "system"


async def test_redelivery_is_idempotent(client, emit, consumer):
    env = await emit("CaseOpened", {"case_id": str(uuid.uuid4())})
    assert await consumer.process_available() == 1

    # publish the SAME envelope again (same event_id)
    from tests.conftest import _BASE_TOPIC
    import json

    from aiokafka import AIOKafkaProducer

    prod = AIOKafkaProducer(bootstrap_servers=__import__("os").environ["EVENTS_KAFKA_BOOTSTRAP"])
    await prod.start()
    try:
        import os

        await prod.send_and_wait(
            os.environ["EVENTS_TOPIC_PREFIX"] + _BASE_TOPIC["CaseOpened"],
            json.dumps(env).encode(),
        )
    finally:
        await prod.stop()

    assert await consumer.process_available() == 0  # no new audit row
    assert len(await _audit_rows()) == 1
    async with OwnerSession() as s:
        consumed = (await s.scalars(select(ConsumedEvent))).all()
    assert len(consumed) == 1


async def test_unmapped_event_is_recorded_consumed_but_not_audited(client, emit, consumer):
    await emit("SomethingUnmapped", {"whatever": 1})
    assert await consumer.process_available() == 0
    assert await _audit_rows() == []
    async with OwnerSession() as s:
        assert len((await s.scalars(select(ConsumedEvent))).all()) == 1  # won't retry


async def test_chain_links_each_entry_to_the_previous(client, emit, consumer):
    for i in range(5):
        await emit("CaseOpened", {"case_id": str(uuid.uuid4()), "n": i})
    assert await consumer.process_available(timeout=5.0) == 5

    rows = await _audit_rows()
    assert rows[0].prev_hash == GENESIS
    for earlier, later in zip(rows, rows[1:]):
        assert later.prev_hash == earlier.record_hash

    async with OwnerSession() as s:
        checked, valid, broken_at = await verify_chain(s)
    assert (checked, valid, broken_at) == (5, True, None)
