"""/integration-settings — admin-editable external-system-log retention (Phase 5).

INTEGRATION_GATEWAY_LOG_RETENTION_DAYS is the seed/default; a PATCH overrides
it at runtime. "ICT Admin" holds integration.settings.{read,write} (iam
migration 0011). Every mutating endpoint here enqueues a domain event, so a
change publishes IntegrationSettingsUpdated (FR-INT-05 / rule 3).
"""
import datetime as dt
import uuid

from sqlalchemy import select

from app.events.models import OutboxEvent
from app.models import ExternalSystemLog
from app.services.retention import RetentionWorker
from tests.conftest import SessionLocal

SETTINGS = "/api/v1/integration-settings"
UTC = dt.timezone.utc


async def _outbox_rows(event_type: str) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        return list(
            (
                await s.scalars(
                    select(OutboxEvent).where(OutboxEvent.event_type == event_type)
                )
            ).all()
        )


async def _make_log(*, age_days: int) -> int:
    async with SessionLocal() as s:
        row = ExternalSystemLog(
            system_name="CAD", direction="outbound", correlation_id=uuid.uuid4()
        )
        s.add(row)
        await s.flush()
        row.created_at = dt.datetime.now(UTC) - dt.timedelta(days=age_days)
        await s.commit()
        return row.id


async def test_get_returns_effective_default(client, auth_ict):
    r = await client.get(SETTINGS, headers=auth_ict)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"values", "overridden"}
    assert body["overridden"] == []
    assert body["values"]["log_retention_days"] == 180  # env default


async def test_get_requires_settings_read(client, auth_none):
    assert (await client.get(SETTINGS, headers=auth_none)).status_code == 403


async def test_patch_requires_settings_write(client, auth_none):
    r = await client.patch(SETTINGS, headers=auth_none, json={"log_retention_days": 90})
    assert r.status_code == 403


async def test_patch_overrides_persists_and_emits_event(client, auth_ict):
    r = await client.patch(SETTINGS, headers=auth_ict, json={"log_retention_days": 90})
    assert r.status_code == 200, r.text
    assert r.json()["values"]["log_retention_days"] == 90
    assert r.json()["overridden"] == ["log_retention_days"]

    g = await client.get(SETTINGS, headers=auth_ict)
    assert g.json()["values"]["log_retention_days"] == 90

    rows = await _outbox_rows("IntegrationSettingsUpdated")
    assert len(rows) == 1
    assert rows[0].topic.endswith("integration.settings_updated")
    assert rows[0].body["payload"]["changed"] == {"log_retention_days": "90"}
    assert rows[0].body["payload"]["actor_id"] is not None
    assert rows[0].body["actor_id"] is not None


async def test_patch_unknown_key_rejected(client, auth_ict):
    r = await client.patch(SETTINGS, headers=auth_ict, json={"retention": 90})
    assert r.status_code in (400, 422)


async def test_patch_invalid_value_rejected(client, auth_ict):
    r = await client.patch(SETTINGS, headers=auth_ict, json={"log_retention_days": 0})
    assert r.status_code in (400, 422)


async def test_empty_patch_is_a_noop(client, auth_ict):
    r = await client.patch(SETTINGS, headers=auth_ict, json={})
    assert r.status_code == 200
    assert r.json()["overridden"] == []
    assert await _outbox_rows("IntegrationSettingsUpdated") == []


async def test_lowering_retention_makes_the_purge_job_delete_a_previously_kept_row(
    client, auth_ict
):
    """The Phase 5 behaviour check: change the setting, confirm the retention
    worker's behaviour actually changes."""
    log_id = await _make_log(age_days=100)

    # default 180d window: the 100-day-old row is still inside it.
    assert await RetentionWorker(SessionLocal).run_once() == 0

    patched = await client.patch(
        SETTINGS, headers=auth_ict, json={"log_retention_days": 90}
    )
    assert patched.status_code == 200

    # now outside the 90-day window -> purged.
    assert await RetentionWorker(SessionLocal).run_once() == 1
    async with SessionLocal() as s:
        assert await s.get(ExternalSystemLog, log_id) is None
