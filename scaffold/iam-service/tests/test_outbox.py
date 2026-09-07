"""TD-003: admin actions + lockout write an outbox event in the same transaction.

FR-IAM-06 (UserCreated / UserDeactivated / UserRoleReassigned),
FR-IAM-05 (AccountLockedOut — exactly once per lockout).
"""
import uuid

import pytest
from sqlalchemy import select

from app import config
from app.events.models import OutboxEvent
from tests.conftest import SessionLocal, auth


async def _rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


def _new_user_body(**over):
    body = {
        "badge_number": f"NEW-{uuid.uuid4().hex[:6]}",
        "password": "Cr3ate!dUserpw",
        "full_name": "New Officer",
        "station_id": str(uuid.uuid4()),
    }
    body.update(over)
    return body


@pytest.fixture
async def admin_token(make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    return await access_token_for(admin)


# --- UserCreated ---------------------------------------------------------
async def test_create_user_makes_the_row_and_one_event(client, admin_token):
    body = _new_user_body(role_ids=[2])  # Patrol Officer
    r = await client.post("/api/v1/users", headers=auth(admin_token), json=body)
    assert r.status_code == 201
    user_id = r.json()["id"]

    # domain change: the account is really there
    got = await client.get(f"/api/v1/users/{user_id}", headers=auth(admin_token))
    assert got.status_code == 200 and got.json()["badge_number"] == body["badge_number"]

    # audit-bound event, written in the same transaction
    rows = await _rows("UserCreated")
    assert len(rows) == 1
    assert rows[0].aggregate_id == user_id
    assert rows[0].topic.endswith("user.created")
    assert rows[0].body["payload"]["user_id"] == user_id
    assert rows[0].body["payload"]["roles"] == ["Patrol Officer"]
    assert rows[0].body["actor_id"] is not None
    assert rows[0].published_at is None


# --- UserDeactivated ---------------------------------------------------
async def test_deactivation_emits_once_only_on_the_transition(
    client, admin_token, make_user
):
    u = await make_user()
    url = f"/api/v1/users/{u.id}"

    r = await client.patch(url, headers=auth(admin_token), json={"status": "deactivated"})
    assert r.status_code == 200 and r.json()["status"] == "deactivated"
    assert len(await _rows("UserDeactivated")) == 1

    # patching to 'deactivated' again is a no-op transition -> no second event
    await client.patch(url, headers=auth(admin_token), json={"status": "deactivated"})
    assert len(await _rows("UserDeactivated")) == 1


async def test_suspend_does_not_emit_userdeactivated(client, admin_token, make_user):
    u = await make_user()
    r = await client.patch(
        f"/api/v1/users/{u.id}", headers=auth(admin_token), json={"status": "suspended"}
    )
    assert r.status_code == 200
    assert await _rows("UserDeactivated") == []


# --- UserUpdated (FR-IAM-06 — non-deactivation admin edits) ------------
async def test_station_reassignment_emits_user_updated(client, admin_token, make_user):
    u = await make_user()
    url = f"/api/v1/users/{u.id}"
    new_station = str(uuid.uuid4())

    r = await client.patch(url, headers=auth(admin_token), json={"station_id": new_station})
    assert r.status_code == 200
    rows = await _rows("UserUpdated")
    assert len(rows) == 1
    assert rows[0].body["payload"]["fields"] == ["station_id"]
    assert rows[0].body["payload"]["station_id"] == new_station

    # a PATCH that changes nothing emits nothing
    await client.patch(url, headers=auth(admin_token), json={"station_id": new_station})
    assert len(await _rows("UserUpdated")) == 1


async def test_deactivating_patch_emits_only_userdeactivated_not_user_updated(
    client, admin_token, make_user
):
    u = await make_user()
    r = await client.patch(
        f"/api/v1/users/{u.id}", headers=auth(admin_token), json={"status": "deactivated"}
    )
    assert r.status_code == 200
    assert len(await _rows("UserDeactivated")) == 1
    assert await _rows("UserUpdated") == []  # status-only deactivation isn't double-reported


# --- UserRoleReassigned ---------------------------------------------
async def test_role_reassignment_emits_only_when_the_set_changes(
    client, admin_token, make_user
):
    u = await make_user(roles=["Patrol Officer"])
    url = f"/api/v1/users/{u.id}/roles"

    r = await client.put(url, headers=auth(admin_token), json={"role_ids": [3]})  # Investigator
    assert r.status_code == 200
    rows = await _rows("UserRoleReassigned")
    assert len(rows) == 1
    assert rows[0].body["payload"]["previous_roles"] == ["Patrol Officer"]
    assert rows[0].body["payload"]["new_roles"] == ["Investigator"]

    # same set again -> no new event
    await client.put(url, headers=auth(admin_token), json={"role_ids": [3]})
    assert len(await _rows("UserRoleReassigned")) == 1


# --- UserPasswordChanged (FR-IAM-06 — TD-003 reopened) ---------------
async def test_self_password_change_emits_user_password_changed(
    client, make_user, access_token_for
):
    user = await make_user(roles=["Patrol Officer"])
    token = await access_token_for(user)
    r = await client.post(
        f"/api/v1/users/{user.id}/password",
        headers=auth(token),
        json={"current_password": user.password, "new_password": "N3w!selfpasswd"},
    )
    assert r.status_code == 204
    rows = await _rows("UserPasswordChanged")
    assert len(rows) == 1
    assert rows[0].body["payload"]["by_admin"] is False
    assert rows[0].body["actor_id"] == str(user.id)  # self-service -> actor is the user


async def test_admin_password_reset_emits_user_password_changed_by_admin(
    client, make_user, access_token_for
):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    target = await make_user()
    r = await client.post(
        f"/api/v1/users/{target.id}/password",
        headers=auth(token),
        json={"new_password": "R3set!byadminpw"},
    )
    assert r.status_code == 204
    rows = await _rows("UserPasswordChanged")
    assert len(rows) == 1
    payload = rows[0].body["payload"]
    assert payload["by_admin"] is True
    assert payload["user_id"] == str(target.id)
    assert rows[0].body["actor_id"] == str(admin.id)


# --- RoleCreated / RolePermissionsChanged (FR-IAM-06 — permission defs) ---
async def test_role_lifecycle_emits_created_then_permissions_changed(client, admin_token):
    created = await client.post(
        "/api/v1/roles", headers=auth(admin_token), json={"name": f"Analyst-{uuid.uuid4().hex[:6]}"}
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    rc = await _rows("RoleCreated")
    assert len(rc) == 1
    assert rc[0].body["payload"]["role_id"] == role_id

    changed = await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        headers=auth(admin_token),
        json={"codes": ["case.read", "audit.read"]},
    )
    assert changed.status_code == 200
    rp = await _rows("RolePermissionsChanged")
    assert len(rp) == 1
    assert rp[0].body["payload"]["previous_permissions"] == []
    assert rp[0].body["payload"]["new_permissions"] == ["audit.read", "case.read"]

    # setting the same permission set again -> no new event
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        headers=auth(admin_token),
        json={"codes": ["audit.read", "case.read"]},
    )
    assert len(await _rows("RolePermissionsChanged")) == 1


# --- AccountLockedOut (FR-IAM-05) ---------------------------------------
async def test_lockout_emits_exactly_once_not_per_failed_attempt(client, make_user):
    pw = "R1ght!Passw0rd"
    u = await make_user(password=pw)
    limit = config.MAX_FAILED_LOGINS

    for _ in range(limit):
        r = await client.post(
            "/api/v1/auth/login",
            json={"badge_number": u.badge_number, "password": "wrong"},
        )
    assert r.status_code == 423  # the last failed attempt locked it

    locked = await _rows("AccountLockedOut")
    assert len(locked) == 1, f"expected exactly one lockout event, got {len(locked)}"
    assert locked[0].body["payload"]["badge_number"] == u.badge_number
    assert locked[0].body["payload"]["failed_login_count"] == limit
    assert locked[0].body["actor_role"] == "system"

    # further attempts on the already-locked account emit nothing new
    for _ in range(3):
        r = await client.post(
            "/api/v1/auth/login",
            json={"badge_number": u.badge_number, "password": "wrong"},
        )
        assert r.status_code == 423
    assert len(await _rows("AccountLockedOut")) == 1

    # even a correct password now still just 423s, no new event
    r = await client.post(
        "/api/v1/auth/login", json={"badge_number": u.badge_number, "password": pw}
    )
    assert r.status_code == 423
    assert len(await _rows("AccountLockedOut")) == 1


async def test_failed_attempts_below_threshold_emit_no_lockout(client, make_user):
    u = await make_user(password="R1ght!Passw0rd")
    for _ in range(config.MAX_FAILED_LOGINS - 1):
        await client.post(
            "/api/v1/auth/login",
            json={"badge_number": u.badge_number, "password": "wrong"},
        )
    assert await _rows("AccountLockedOut") == []


# --- relay -> Kafka --------------------------------------------------------
async def test_relay_publishes_admin_events(client, admin_token, outbox_relay, read_kafka):
    r = await client.post(
        "/api/v1/users", headers=auth(admin_token), json=_new_user_body()
    )
    user_id = r.json()["id"]

    assert await outbox_relay.drain_once() == 1
    assert (await _rows("UserCreated"))[0].published_at is not None

    events = await read_kafka("UserCreated", expected=1)
    assert len(events) == 1
    assert events[0]["event_type"] == "UserCreated"
    assert events[0]["payload"]["user_id"] == user_id
    assert events[0]["service"] == "iam-service"
