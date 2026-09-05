"""Transactional outbox: same-transaction enqueue + relay-to-Kafka (SRS §3.4)."""
import uuid

from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal


async def _outbox_rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


async def test_config_toggle_enqueues(client, auth_ict):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    cad = next(c for c in r.json() if c["system_name"] == "CAD")
    await client.patch(
        f"/api/v1/integration-configs/{cad['id']}",
        json={"enabled": False},
        headers=auth_ict,
    )

    rows = await _outbox_rows("IntegrationConfigUpdated")
    assert len(rows) == 1
    assert rows[0].topic.endswith("integration.config_updated")
    assert rows[0].body["payload"]["system_name"] == "CAD"
    assert rows[0].body["payload"]["enabled"] is False
    assert rows[0].body["actor_id"] is not None


async def test_adapter_call_enqueues_external_system_call_logged(client, auth_ict):
    corr = str(uuid.uuid4())
    await client.post(
        "/api/v1/adapters/CAD/call",
        json={"x": 1},
        headers={**auth_ict, "X-Correlation-Id": corr},
    )
    rows = await _outbox_rows("ExternalSystemCallLogged")
    assert len(rows) == 1
    assert rows[0].aggregate_id == corr
    assert rows[0].body["payload"]["system_name"] == "CAD"
    assert rows[0].body["payload"]["correlation_id"] == corr


async def test_failed_adapter_call_writes_no_outbox_row(client, auth_ict):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    cad = next(c for c in r.json() if c["system_name"] == "CAD")
    await client.patch(
        f"/api/v1/integration-configs/{cad['id']}",
        json={"enabled": False},
        headers=auth_ict,
    )
    # 1 row from the toggle; the disabled-system call adds none.
    await client.post("/api/v1/adapters/CAD/call", json={}, headers=auth_ict)
    assert len(await _outbox_rows("ExternalSystemCallLogged")) == 0


async def test_relay_publishes_to_kafka_and_marks_sent(client, auth_ict, outbox_relay, read_kafka):
    corr = str(uuid.uuid4())
    await client.post(
        "/api/v1/adapters/NCDB/call",
        json={},
        headers={**auth_ict, "X-Correlation-Id": corr},
    )

    published = await outbox_relay.drain_once()
    assert published == 1

    rows = await _outbox_rows("ExternalSystemCallLogged")
    assert rows[0].published_at is not None

    events = await read_kafka("ExternalSystemCallLogged", expected=1)
    assert len(events) == 1
    assert events[0]["event_type"] == "ExternalSystemCallLogged"
    assert events[0]["aggregate_id"] == corr

    assert await outbox_relay.drain_once() == 0
