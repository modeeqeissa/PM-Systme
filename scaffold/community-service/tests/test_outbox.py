"""Transactional outbox: same-transaction enqueue + relay-to-Kafka (SRS §3.4)."""
import datetime as dt
import uuid

from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal
from tests.test_follow_up_actions import _backdate_due_date


async def _outbox_rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


async def test_meeting_logged_enqueues(client, auth_comm):
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": str(uuid.uuid4()),
            "facilitator_id": str(uuid.uuid4()),
            "meeting_date": "2026-06-15",
            "location": "OUTBOX-HALL",
        },
        headers=auth_comm,
    )
    meeting_id = r.json()["id"]

    rows = await _outbox_rows("MeetingLogged")
    assert len(rows) == 1
    assert rows[0].aggregate_id == meeting_id
    assert rows[0].topic.endswith("community.meeting_logged")
    assert rows[0].body["actor_id"] is not None  # came from the JWT


async def test_concern_logged_and_status_changed_enqueue(client, auth_comm):
    r = await client.post(
        "/api/v1/concerns", json={"category": "safety"}, headers=auth_comm
    )
    concern_id = r.json()["id"]
    await client.patch(
        f"/api/v1/concerns/{concern_id}", json={"status": "resolved"}, headers=auth_comm
    )

    logged = await _outbox_rows("ConcernLogged")
    changed = await _outbox_rows("ConcernStatusChanged")
    assert len(logged) == 1 and logged[0].aggregate_id == concern_id
    assert len(changed) == 1
    assert changed[0].body["payload"]["from_status"] == "open"
    assert changed[0].body["payload"]["to_status"] == "resolved"


async def test_follow_up_action_created_and_completed_enqueue(client, auth_comm, make_concern):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]
    await client.patch(
        f"/api/v1/follow-up-actions/{action_id}",
        json={"status": "completed"},
        headers=auth_comm,
    )

    created = await _outbox_rows("FollowUpActionCreated")
    changed = await _outbox_rows("FollowUpActionStatusChanged")
    assert len(created) == 1 and created[0].aggregate_id == action_id
    assert len(changed) == 1
    assert changed[0].body["payload"]["to_status"] == "completed"


async def test_recompute_overdue_enqueues(client, auth_comm, make_concern, today):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]
    await _backdate_due_date(action_id, today - dt.timedelta(days=1))

    await client.post("/api/v1/follow-up-actions/recompute-status", headers=auth_comm)

    rows = await _outbox_rows("FollowUpActionStatusChanged")
    assert len(rows) == 1
    assert rows[0].body["payload"]["from_status"] == "pending"
    assert rows[0].body["payload"]["to_status"] == "overdue"


async def test_event_id_is_unique(client, auth_comm):
    for i in range(3):
        await client.post(
            "/api/v1/concerns", json={"category": f"cat-{i}"}, headers=auth_comm
        )
    rows = await _outbox_rows("ConcernLogged")
    ids = [str(r.event_id) for r in rows]
    assert len(ids) == len(set(ids)) == 3


async def test_relay_publishes_meeting_logged_to_kafka_and_marks_sent(
    client, auth_comm, outbox_relay, read_kafka
):
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": str(uuid.uuid4()),
            "facilitator_id": str(uuid.uuid4()),
            "meeting_date": "2026-06-15",
            "location": "OUTBOX-KAFKA",
        },
        headers=auth_comm,
    )
    meeting_id = r.json()["id"]

    published = await outbox_relay.drain_once()
    assert published == 1

    rows = await _outbox_rows("MeetingLogged")
    assert rows[0].published_at is not None

    events = await read_kafka("MeetingLogged", expected=1)
    assert len(events) == 1
    assert events[0]["event_type"] == "MeetingLogged"
    assert events[0]["aggregate_id"] == meeting_id

    assert await outbox_relay.drain_once() == 0  # already published, no-op


async def test_recompute_task_sweep_once_matches_endpoint_behavior(
    client, auth_comm, make_concern, today, recompute_task
):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]
    await _backdate_due_date(action_id, today - dt.timedelta(days=1))

    updated = await recompute_task.sweep_once()
    assert updated == 1

    r = await client.get(f"/api/v1/follow-up-actions/{action_id}", headers=auth_comm)
    assert r.json()["status"] == "overdue"

    rows = await _outbox_rows("FollowUpActionStatusChanged")
    assert len(rows) == 1
    assert rows[0].body["actor_role"] == "system:recompute-task"
