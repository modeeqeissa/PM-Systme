"""Transactional outbox: same-transaction enqueue + relay-to-Kafka (SRS §3.4)."""
import uuid

import pytest
from sqlalchemy import select, text

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal


async def _outbox_rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


async def test_incident_reported_enqueued_once_and_not_on_replay(client, auth_rw):
    key = str(uuid.uuid4())
    body = {
        "reported_by": str(uuid.uuid4()),
        "incident_type": "theft",
        "description": "bike stolen",
        "station_id": str(uuid.uuid4()),
        "reported_at": "2026-09-03T08:00:00+00:00",
    }
    r1 = await client.post(
        "/api/v1/incidents", json=body, headers={**auth_rw, "Idempotency-Key": key}
    )
    assert r1.status_code == 201
    r2 = await client.post(  # idempotent replay
        "/api/v1/incidents", json=body, headers={**auth_rw, "Idempotency-Key": key}
    )
    assert r2.status_code == 200

    rows = await _outbox_rows("IncidentReported")
    assert len(rows) == 1  # replay did NOT re-emit
    assert rows[0].aggregate_id == r1.json()["id"]
    assert rows[0].topic.endswith("incident.reported")
    assert rows[0].body["payload"]["incident_type"] == "theft"


async def test_case_opened_row_written_in_same_transaction(client, auth_rw):
    r = await client.post(
        "/api/v1/cases", json={"lead_officer_id": str(uuid.uuid4())}, headers=auth_rw
    )
    assert r.status_code == 201
    case_id = r.json()["id"]

    rows = await _outbox_rows("CaseOpened")
    assert len(rows) == 1
    row = rows[0]
    assert row.aggregate_id == case_id
    assert row.published_at is None
    assert row.topic.endswith("case.opened")
    assert row.body["payload"]["case_number"] == r.json()["case_number"]
    assert row.body["event_type"] == "CaseOpened"


async def test_failed_status_transition_writes_no_outbox_row(client, make_case, auth_rw):
    case = await make_case(status="closed")  # terminal
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": "open"}, headers=auth_rw
    )
    assert r.status_code == 409
    assert await _outbox_rows("CaseStatusChanged") == []  # rolled back with the write


async def test_status_change_and_arrest_enqueue_events(client, make_case, auth_rw):
    case = await make_case(status="open")
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "investigating"},
        headers=auth_rw,
    )
    assert r.status_code == 200
    r = await client.post(
        f"/api/v1/cases/{case.id}/arrests",
        json={
            "officer_id": str(uuid.uuid4()),
            "suspect_id": str(uuid.uuid4()),
            "arrest_date": "2026-09-03T12:00:00+00:00",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201

    scs = await _outbox_rows("CaseStatusChanged")
    arr = await _outbox_rows("ArrestRecorded")
    assert len(scs) == 1 and scs[0].body["payload"]["to_status"] == "investigating"
    assert len(arr) == 1 and arr[0].body["payload"]["case_id"] == str(case.id)
    # actor came from the JWT
    assert scs[0].body["actor_id"] is not None


async def test_statement_recorded_enqueued(client, make_case, auth_rw):
    case = await make_case(status="open")
    r = await client.post(
        f"/api/v1/cases/{case.id}/statements",
        json={
            "recorded_by": str(uuid.uuid4()),
            "party_type": "witness",
            "statement_text": "I saw everything from across the street.",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201

    rows = await _outbox_rows("StatementRecorded")
    assert len(rows) == 1
    assert rows[0].aggregate_id == r.json()["id"]
    assert rows[0].topic.endswith("case.statement_recorded")
    assert rows[0].body["payload"]["party_type"] == "witness"


async def test_relay_publishes_to_kafka_and_marks_sent(
    client, auth_rw, outbox_relay, read_kafka
):
    r = await client.post(
        "/api/v1/cases", json={"lead_officer_id": str(uuid.uuid4())}, headers=auth_rw
    )
    case_id = r.json()["id"]

    published = await outbox_relay.drain_once()
    assert published == 1

    rows = await _outbox_rows("CaseOpened")
    assert rows[0].published_at is not None
    assert rows[0].attempts == 1

    events = await read_kafka("CaseOpened", expected=1)
    assert len(events) == 1
    assert events[0]["event_type"] == "CaseOpened"
    assert events[0]["payload"]["case_id"] == case_id
    assert events[0]["aggregate_id"] == case_id

    # draining again is a no-op (already published)
    assert await outbox_relay.drain_once() == 0


async def test_event_id_is_unique(client, auth_rw):
    for _ in range(3):
        await client.post(
            "/api/v1/cases",
            json={"lead_officer_id": str(uuid.uuid4())},
            headers=auth_rw,
        )
    async with SessionLocal() as s:
        ids = (await s.execute(text("SELECT event_id FROM outbox_events"))).scalars().all()
    assert len(ids) == len(set(ids)) == 3
