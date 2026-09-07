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


async def test_hash_mismatch_enqueues_event_but_a_match_does_not(client, auth_full):
    content = b"authentic " + uuid.uuid4().bytes
    ev = (
        await client.post(
            "/api/v1/evidence",
            data=_form(),
            files={"file": ("f.bin", content, "application/octet-stream")},
            headers=auth_full,
        )
    ).json()

    # a clean verify -> no event
    r = await client.post(f"/api/v1/evidence/{ev['id']}/verify", headers=auth_full)
    assert r.status_code == 200 and r.json()["match"] is True
    assert await _rows("EvidenceHashMismatch") == []

    # tamper with the vault blob, verify again -> mismatch + one event
    from app.services import vault

    with open(f"{vault.config.vault_dir()}/{ev['storage_ref']}", "wb") as fh:
        fh.write(vault._fernet().encrypt(b"tampered"))
    r = await client.post(f"/api/v1/evidence/{ev['id']}/verify", headers=auth_full)
    assert r.status_code == 200 and r.json()["match"] is False

    rows = await _rows("EvidenceHashMismatch")
    assert len(rows) == 1
    assert rows[0].topic.endswith("evidence.hash_mismatch")
    assert rows[0].body["payload"]["evidence_id"] == ev["id"]
    assert rows[0].body["payload"]["stored_hash"] != rows[0].body["payload"]["computed_hash"]
    assert rows[0].body["actor_id"] is not None


async def test_verify_always_enqueues_evidence_file_verified(client, auth_full):
    """FR-AUD-01: reading + hashing the stored file is audited on every verify,
    match or not — separate from EvidenceHashMismatch."""
    content = b"authentic " + uuid.uuid4().bytes
    form = _form()
    ev = (
        await client.post(
            "/api/v1/evidence",
            data=form,
            files={"file": ("f.bin", content, "application/octet-stream")},
            headers=auth_full,
        )
    ).json()

    r = await client.post(f"/api/v1/evidence/{ev['id']}/verify", headers=auth_full)
    assert r.status_code == 200 and r.json()["match"] is True

    verified = await _rows("EvidenceFileVerified")
    assert len(verified) == 1
    assert verified[0].topic.endswith("evidence.file_verified")
    assert verified[0].body["payload"]["evidence_id"] == ev["id"]
    assert verified[0].body["payload"]["case_id"] == form["case_id"]
    assert verified[0].body["payload"]["match"] is True
    assert "verified_at" in verified[0].body["payload"]
    assert await _rows("EvidenceHashMismatch") == []


async def test_custody_chain_read_enqueues_event(client, make_item, auth_full):
    """FR-AUD-01: reading the full custody chain is audited."""
    item = await make_item()
    await client.post(
        f"/api/v1/evidence/{item.id}/custody",
        json={"action": "stored", "from_officer": str(uuid.uuid4())},
        headers=auth_full,
    )
    r = await client.get(f"/api/v1/evidence/{item.id}/custody", headers=auth_full)
    assert r.status_code == 200
    chain_len = len(r.json())

    reads = await _rows("CustodyChainRead")
    assert len(reads) == 1
    assert reads[0].topic.endswith("evidence.custody_chain_read")
    assert reads[0].body["payload"]["evidence_id"] == str(item.id)
    assert reads[0].body["payload"]["event_count"] == chain_len
    assert reads[0].body["actor_id"] is not None


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
