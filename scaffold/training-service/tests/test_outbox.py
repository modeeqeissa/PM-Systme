"""Transactional outbox: same-transaction enqueue + relay-to-Kafka (SRS §3.4)."""
import datetime as dt
import uuid

from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal
from tests.test_officer_certifications import _set_expires_date


async def _outbox_rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


async def test_course_created_updated_deleted_all_enqueue(client, auth_train):
    r = await client.post(
        "/api/v1/courses",
        json={"title": "OUTBOX-COURSE", "validity_months": 12},
        headers=auth_train,
    )
    course_id = r.json()["id"]
    await client.patch(
        f"/api/v1/courses/{course_id}", json={"mandatory": True}, headers=auth_train
    )
    await client.delete(f"/api/v1/courses/{course_id}", headers=auth_train)

    created = await _outbox_rows("CourseCreated")
    updated = await _outbox_rows("CourseUpdated")
    deleted = await _outbox_rows("CourseDeleted")
    assert len(created) == len(updated) == len(deleted) == 1
    assert created[0].aggregate_id == str(course_id)
    assert created[0].topic.endswith("training.course_created")
    assert updated[0].body["payload"]["fields"] == ["mandatory"]
    assert deleted[0].aggregate_id == str(course_id)
    assert created[0].body["actor_id"] is not None  # came from the JWT


async def test_certification_created_and_deleted_enqueue(client, auth_train, make_course):
    course = await make_course()
    r = await client.post(
        "/api/v1/certifications", json={"course_id": course.id}, headers=auth_train
    )
    cert_id = r.json()["id"]
    await client.delete(f"/api/v1/certifications/{cert_id}", headers=auth_train)

    created = await _outbox_rows("CertificationCreated")
    deleted = await _outbox_rows("CertificationDeleted")
    assert len(created) == 1 and created[0].aggregate_id == str(cert_id)
    assert len(deleted) == 1 and deleted[0].aggregate_id == str(cert_id)


async def test_officer_certification_issued_enqueues(client, auth_train, make_certification):
    cert = await make_certification()
    officer_id = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": officer_id, "certification_id": cert.id},
        headers=auth_train,
    )
    officer_cert_id = r.json()["id"]

    rows = await _outbox_rows("OfficerCertificationIssued")
    assert len(rows) == 1
    assert rows[0].aggregate_id == officer_cert_id
    assert rows[0].body["payload"]["officer_id"] == officer_id
    assert rows[0].body["payload"]["status"] == "active"


async def test_recompute_status_change_enqueues(client, auth_train, make_certification, today):
    cert = await make_certification()
    r = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    officer_cert_id = r.json()["id"]
    await _set_expires_date(officer_cert_id, today - dt.timedelta(days=1))

    await client.post("/api/v1/officer-certifications/recompute-status", headers=auth_train)

    rows = await _outbox_rows("OfficerCertificationStatusChanged")
    assert len(rows) == 1
    assert rows[0].aggregate_id == officer_cert_id
    assert rows[0].body["payload"]["from_status"] == "active"
    assert rows[0].body["payload"]["to_status"] == "expired"


async def test_event_id_is_unique(client, auth_train):
    for i in range(3):
        await client.post(
            "/api/v1/courses",
            json={"title": f"Course-{i}", "validity_months": 6},
            headers=auth_train,
        )
    rows = await _outbox_rows("CourseCreated")
    ids = [str(r.event_id) for r in rows]
    assert len(ids) == len(set(ids)) == 3


async def test_relay_publishes_course_created_to_kafka_and_marks_sent(
    client, auth_train, outbox_relay, read_kafka
):
    r = await client.post(
        "/api/v1/courses",
        json={"title": "OUTBOX-KAFKA", "validity_months": 12},
        headers=auth_train,
    )
    course_id = r.json()["id"]

    published = await outbox_relay.drain_once()
    assert published == 1

    rows = await _outbox_rows("CourseCreated")
    assert rows[0].published_at is not None

    events = await read_kafka("CourseCreated", expected=1)
    assert len(events) == 1
    assert events[0]["event_type"] == "CourseCreated"
    assert events[0]["aggregate_id"] == str(course_id)

    assert await outbox_relay.drain_once() == 0  # already published, no-op


async def test_recompute_task_sweep_once_matches_endpoint_behavior(
    client, auth_train, make_certification, today, recompute_task
):
    """app.services.recompute_task.RecomputeTask (the periodic background sweep)
    shares the same recompute logic as POST /officer-certifications/recompute-status."""
    cert = await make_certification()
    r = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    officer_cert_id = r.json()["id"]
    await _set_expires_date(officer_cert_id, today + dt.timedelta(days=5))

    updated = await recompute_task.sweep_once()
    assert updated == 1

    r = await client.get(f"/api/v1/officer-certifications/{officer_cert_id}", headers=auth_train)
    assert r.json()["status"] == "expiring_soon"

    rows = await _outbox_rows("OfficerCertificationStatusChanged")
    assert len(rows) == 1
    assert rows[0].body["actor_role"] == "system:recompute-task"
