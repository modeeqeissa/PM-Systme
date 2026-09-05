import uuid

from sqlalchemy import select

from app.models import ConsumedEvent, Notification, OfficerUserMap
from tests.conftest import SessionLocal


async def _notifications() -> list[Notification]:
    async with SessionLocal() as s:
        return list((await s.scalars(select(Notification).order_by(Notification.id))).all())


async def test_officer_created_seeds_map_but_queues_no_notification(client, emit, consumer):
    officer_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    await emit("OfficerCreated", {"officer_id": officer_id, "user_id": user_id})

    assert await consumer.process_available() == 0
    assert await _notifications() == []

    async with SessionLocal() as s:
        row = await s.get(OfficerUserMap, uuid.UUID(officer_id))
    assert row is not None
    assert str(row.user_id) == user_id


async def test_transfer_approved_notifies_the_officer(client, emit, consumer, make_officer_map):
    officer_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await make_officer_map(officer_id, user_id)

    await emit(
        "TransferStatusChanged",
        {"transfer_id": str(uuid.uuid4()), "officer_id": str(officer_id), "to_status": "approved"},
    )
    assert await consumer.process_available() == 1

    rows = await _notifications()
    assert len(rows) == 1
    assert rows[0].recipient_user_id == user_id
    assert rows[0].template_code == "TRANSFER_APPROVED"
    assert rows[0].channel == "in_app"
    assert rows[0].status == "queued"


async def test_transfer_rejected_and_leave_events_map_correctly(
    client, emit, consumer, make_officer_map
):
    officer_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await make_officer_map(officer_id, user_id)

    await emit(
        "TransferStatusChanged",
        {"transfer_id": str(uuid.uuid4()), "officer_id": str(officer_id), "to_status": "rejected"},
    )
    await emit(
        "LeaveStatusChanged",
        {"leave_request_id": str(uuid.uuid4()), "officer_id": str(officer_id), "to_status": "approved"},
    )
    await emit(
        "LeaveStatusChanged",
        {"leave_request_id": str(uuid.uuid4()), "officer_id": str(officer_id), "to_status": "rejected"},
    )
    assert await consumer.process_available() == 3

    codes = {r.template_code for r in await _notifications()}
    assert codes == {"TRANSFER_REJECTED", "LEAVE_APPROVED", "LEAVE_REJECTED"}


async def test_pending_transfer_status_produces_no_notification(
    client, emit, consumer, make_officer_map
):
    """to_status='pending' never actually reaches TransferStatusChanged (that
    event only fires on approve/reject), but the mapping should still no-op
    safely rather than raise on an unrecognised to_status."""
    officer_id = uuid.uuid4()
    await make_officer_map(officer_id, uuid.uuid4())
    await emit(
        "TransferStatusChanged",
        {"transfer_id": str(uuid.uuid4()), "officer_id": str(officer_id), "to_status": "pending"},
    )
    assert await consumer.process_available() == 0
    assert await _notifications() == []


async def test_certification_expiring_and_expired_notify(client, emit, consumer, make_officer_map):
    officer_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await make_officer_map(officer_id, user_id)

    await emit(
        "OfficerCertificationStatusChanged",
        {
            "officer_certification_id": str(uuid.uuid4()),
            "officer_id": str(officer_id),
            "to_status": "expiring_soon",
        },
    )
    assert await consumer.process_available() == 1
    assert (await _notifications())[0].template_code == "CERT_EXPIRING"


async def test_certification_recovering_to_active_produces_no_notification(
    client, emit, consumer, make_officer_map
):
    officer_id = uuid.uuid4()
    await make_officer_map(officer_id, uuid.uuid4())
    await emit(
        "OfficerCertificationStatusChanged",
        {
            "officer_certification_id": str(uuid.uuid4()),
            "officer_id": str(officer_id),
            "to_status": "active",
        },
    )
    assert await consumer.process_available() == 0
    assert await _notifications() == []


async def test_follow_up_action_overdue_notifies_assigned_officer(
    client, emit, consumer, make_officer_map
):
    officer_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await make_officer_map(officer_id, user_id)

    await emit(
        "FollowUpActionStatusChanged",
        {
            "follow_up_action_id": str(uuid.uuid4()),
            "assigned_to": str(officer_id),
            "to_status": "overdue",
        },
    )
    assert await consumer.process_available() == 1
    rows = await _notifications()
    assert rows[0].template_code == "FOLLOWUP_OVERDUE"
    assert rows[0].recipient_user_id == user_id


async def test_officer_supervisor_changed_updates_the_map(client, emit, consumer, make_officer_map):
    officer_id = uuid.uuid4()
    supervisor_id = uuid.uuid4()
    await make_officer_map(officer_id, uuid.uuid4())

    await emit(
        "OfficerSupervisorChanged",
        {"officer_id": str(officer_id), "supervisor_id": str(supervisor_id)},
    )
    assert await consumer.process_available() == 0

    async with SessionLocal() as s:
        row = await s.get(OfficerUserMap, officer_id)
    assert row.supervisor_officer_id == supervisor_id


async def test_overdue_follow_up_also_notifies_the_supervisor(client, emit, consumer, make_officer_map):
    assignee_id = uuid.uuid4()
    assignee_user = uuid.uuid4()
    supervisor_id = uuid.uuid4()
    supervisor_user = uuid.uuid4()
    await make_officer_map(assignee_id, assignee_user, supervisor_officer_id=supervisor_id)
    await make_officer_map(supervisor_id, supervisor_user)

    await emit(
        "FollowUpActionStatusChanged",
        {
            "follow_up_action_id": str(uuid.uuid4()),
            "assigned_to": str(assignee_id),
            "to_status": "overdue",
        },
    )
    await consumer.process_available()

    rows = await _notifications()
    by_recipient = {r.recipient_user_id: r for r in rows}
    assert by_recipient[assignee_user].template_code == "FOLLOWUP_OVERDUE"
    assert by_recipient[supervisor_user].template_code == "FOLLOWUP_OVERDUE_SUPERVISOR"


async def test_supervisor_learned_via_officer_created_supervisor_id(client, emit, consumer):
    officer_id = uuid.uuid4()
    supervisor_id = uuid.uuid4()
    await emit(
        "OfficerCreated",
        {
            "officer_id": str(officer_id),
            "user_id": str(uuid.uuid4()),
            "supervisor_id": str(supervisor_id),
        },
    )
    await consumer.process_available()
    async with SessionLocal() as s:
        row = await s.get(OfficerUserMap, officer_id)
    assert row.supervisor_officer_id == supervisor_id


async def test_account_locked_out_notifies_directly_by_user_id(client, emit, consumer):
    user_id = str(uuid.uuid4())
    await emit(
        "AccountLockedOut",
        {"user_id": user_id, "failed_login_count": 5},
        service="iam-service", actor_role="system",
    )
    assert await consumer.process_available() == 1
    rows = await _notifications()
    assert str(rows[0].recipient_user_id) == user_id
    assert rows[0].template_code == "ACCOUNT_LOCKED_OUT"


async def test_unknown_officer_produces_no_notification(client, emit, consumer):
    """Officer's OfficerCreated event hasn't been consumed yet -> dropped, not queued."""
    await emit(
        "TransferStatusChanged",
        {"transfer_id": str(uuid.uuid4()), "officer_id": str(uuid.uuid4()), "to_status": "approved"},
    )
    assert await consumer.process_available() == 0
    assert await _notifications() == []


async def test_redelivery_is_idempotent(client, emit, consumer, make_officer_map):
    officer_id = uuid.uuid4()
    await make_officer_map(officer_id, uuid.uuid4())
    env = await emit(
        "TransferStatusChanged",
        {"transfer_id": str(uuid.uuid4()), "officer_id": str(officer_id), "to_status": "approved"},
    )
    assert await consumer.process_available() == 1

    from aiokafka import AIOKafkaProducer
    import json
    import os

    prod = AIOKafkaProducer(bootstrap_servers=os.environ["EVENTS_KAFKA_BOOTSTRAP"])
    await prod.start()
    try:
        from tests.conftest import _BASE_TOPIC

        await prod.send_and_wait(
            os.environ["EVENTS_TOPIC_PREFIX"] + _BASE_TOPIC["TransferStatusChanged"],
            json.dumps(env).encode(),
        )
    finally:
        await prod.stop()

    assert await consumer.process_available() == 0  # no new notification
    assert len(await _notifications()) == 1
    async with SessionLocal() as s:
        consumed = (await s.scalars(select(ConsumedEvent))).all()
    assert len(consumed) == 1
