"""/notification-settings — admin-editable retention window (Phase 5).

NOTIFICATION_RETENTION_DAYS is the seed/default; a PATCH overrides it at
runtime. "ICT Admin" holds notification.settings.{read,write} (iam
migration 0011). notification_db has no outbox, so a change emits no event
(consistent with PUT /notification-preferences, TD-006).
"""
import datetime as dt

from app.services.retention import RetentionWorker
from tests.conftest import SessionLocal

SETTINGS = "/api/v1/notification-settings"
UTC = dt.timezone.utc


async def test_get_returns_effective_default(client, auth_admin):
    r = await client.get(SETTINGS, headers=auth_admin)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"values", "overridden"}
    assert body["overridden"] == []
    assert body["values"]["retention_days"] == 90  # NOTIFICATION_RETENTION_DAYS default


async def test_get_requires_settings_read(client, auth_user1):
    assert (await client.get(SETTINGS, headers=auth_user1)).status_code == 403


async def test_patch_requires_settings_write(client, auth_user1):
    r = await client.patch(SETTINGS, headers=auth_user1, json={"retention_days": 30})
    assert r.status_code == 403


async def test_patch_overrides_and_persists(client, auth_admin):
    r = await client.patch(SETTINGS, headers=auth_admin, json={"retention_days": 30})
    assert r.status_code == 200, r.text
    assert r.json()["values"]["retention_days"] == 30
    assert r.json()["overridden"] == ["retention_days"]

    g = await client.get(SETTINGS, headers=auth_admin)
    assert g.json()["values"]["retention_days"] == 30
    assert g.json()["overridden"] == ["retention_days"]


async def test_patch_unknown_key_rejected(client, auth_admin):
    r = await client.patch(SETTINGS, headers=auth_admin, json={"retention_dayz": 30})
    assert r.status_code in (400, 422)  # extra=forbid -> 422 at the schema layer


async def test_patch_invalid_value_rejected(client, auth_admin):
    r = await client.patch(SETTINGS, headers=auth_admin, json={"retention_days": 0})
    assert r.status_code in (400, 422)


async def test_empty_patch_is_a_noop(client, auth_admin):
    r = await client.patch(SETTINGS, headers=auth_admin, json={})
    assert r.status_code == 200
    assert r.json()["overridden"] == []


async def test_lowering_retention_makes_the_purge_job_delete_a_previously_kept_row(
    client, auth_admin, make_notification
):
    """The Phase 5 behaviour check: change the setting, confirm the retention
    worker's behaviour actually changes — not just that the row updated."""
    now = dt.datetime.now(UTC)
    n = await make_notification(created_at=now - dt.timedelta(days=40))

    # default 90d window: the 40-day-old row is still inside it.
    assert await RetentionWorker(SessionLocal).run_once() == 0

    patched = await client.patch(
        SETTINGS, headers=auth_admin, json={"retention_days": 30}
    )
    assert patched.status_code == 200

    # now outside the 30-day window -> purged.
    assert await RetentionWorker(SessionLocal).run_once() == 1
