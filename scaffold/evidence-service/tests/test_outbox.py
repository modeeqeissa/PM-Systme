"""Transactional outbox: same-transaction enqueue + relay-to-Kafka (SRS §3.4).

Also proves the least-privilege ``evidence_service_app`` role has exactly the
rights the relay needs on outbox_events (SELECT/INSERT/UPDATE) and no more.
"""
import hashlib
import uuid

from sqlalchemy import select, text

from app.events.models import OutboxEvent
from tests.conftest import AppSession, OwnerSession, app_role_conn


def _form(**over) -> dict:
    d = {
        "case_id": str(uuid.uuid4()),
        "item_type": "digital_file",
        "description": "disk image",
        "collected_by": str(uuid.uuid4()),
        "collected_at": "2026-09-03T10:00:00+00:00",
    }
    d.update(over)
    return d


async def _rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with OwnerSession() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


async def test_evidence_logged_row_written_in_same_transaction(client, auth_full):
    content = b"payload " + uuid.uuid4().bytes
    r = await client.post(
        "/api/v1/evidence",
        data=_form(),
        files={"file": ("f.bin", content, "application/octet-stream")},
        headers=auth_full,
    )
    assert r.status_code == 201
    rows = await _rows("EvidenceLogged")
    assert len(rows) == 1
    assert rows[0].aggregate_id == r.json()["id"]
    assert rows[0].published_at is None
    assert rows[0].topic.endswith("evidence.logged")
    assert rows[0].body["payload"]["sha256_hash"] == hashlib.sha256(content).hexdigest()


async def test_custody_event_recorded_enqueued(client, make_item, auth_full):
    item = await make_item()
    r = await client.post(
        f"/api/v1/evidence/{item.id}/custody",
        json={"action": "stored", "from_officer": str(uuid.uuid4())},
        headers=auth_full,
    )
    assert r.status_code == 201
    rows = await _rows("CustodyEventRecorded")
    assert len(rows) == 1
    assert rows[0].body["payload"]["action"] == "stored"
    assert rows[0].body["payload"]["evidence_id"] == str(item.id)
    assert rows[0].body["actor_id"] is not None


async def test_rejected_custody_write_leaves_no_outbox_row(client, make_item, auth_full):
    item = await make_item()
    # transferred without acknowledgement -> 400, whole transaction rolls back
    r = await client.post(
        f"/api/v1/evidence/{item.id}/custody",
        json={"action": "transferred"},
        headers=auth_full,
    )
    assert r.status_code == 400
    assert await _rows("CustodyEventRecorded") == []


async def test_relay_publishes_to_kafka_and_marks_sent(
    client, make_item, auth_full, outbox_relay, read_kafka
):
    item = await make_item()
    await client.post(
        f"/api/v1/evidence/{item.id}/custody",
        json={
            "action": "transferred",
            "to_officer": str(uuid.uuid4()),
            "acknowledgement_signature": "pin-1",
        },
        headers=auth_full,
    )

    assert await outbox_relay.drain_once() == 1
    rows = await _rows("CustodyEventRecorded")
    assert rows[0].published_at is not None and rows[0].attempts == 1

    events = await read_kafka("CustodyEventRecorded", expected=1)
    assert events[0]["event_type"] == "CustodyEventRecorded"
    assert events[0]["payload"]["evidence_id"] == str(item.id)
    assert events[0]["payload"]["acknowledgement"] is True

    assert await outbox_relay.drain_once() == 0


def test_app_role_can_select_insert_update_but_not_delete_outbox():
    conn = app_role_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM outbox_events")  # SELECT ok
            eid = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO outbox_events (event_id, topic, event_type, "
                "aggregate_type, aggregate_id, body) VALUES (%s,'t','T','x','x','{}')",
                (eid,),
            )  # INSERT ok
            cur.execute(
                "UPDATE outbox_events SET published_at = now() WHERE event_id = %s",
                (eid,),
            )  # UPDATE ok (the relay needs it)
            import psycopg2

            try:
                cur.execute("DELETE FROM outbox_events WHERE event_id = %s", (eid,))
                raise AssertionError("app role should not be able to DELETE outbox rows")
            except psycopg2.errors.InsufficientPrivilege:
                pass
    finally:
        conn.close()
