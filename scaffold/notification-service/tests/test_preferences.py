"""FR-NOTIF-02 — a user's own notification channel preferences (self-scoped)."""


async def test_preferences_start_empty(client, auth_user1):
    r = await client.get("/api/v1/notification-preferences", headers=auth_user1)
    assert r.status_code == 200
    assert r.json() == []


async def test_set_and_read_back_preference(client, auth_user1):
    r = await client.put(
        "/api/v1/notification-preferences",
        json={"channel": "email", "enabled": False},
        headers=auth_user1,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"channel": "email", "enabled": False}

    r = await client.get("/api/v1/notification-preferences", headers=auth_user1)
    assert r.json() == [{"channel": "email", "enabled": False}]


async def test_put_is_an_upsert(client, auth_user1):
    await client.put(
        "/api/v1/notification-preferences",
        json={"channel": "sms", "enabled": False},
        headers=auth_user1,
    )
    r = await client.put(
        "/api/v1/notification-preferences",
        json={"channel": "sms", "enabled": True},
        headers=auth_user1,
    )
    assert r.json()["enabled"] is True

    r = await client.get("/api/v1/notification-preferences", headers=auth_user1)
    assert len(r.json()) == 1


async def test_preferences_are_self_scoped(client, auth_user1, auth_user2):
    await client.put(
        "/api/v1/notification-preferences",
        json={"channel": "push", "enabled": False},
        headers=auth_user1,
    )
    r = await client.get("/api/v1/notification-preferences", headers=auth_user2)
    assert r.json() == []


async def test_preferences_require_auth(client):
    assert (await client.get("/api/v1/notification-preferences")).status_code == 401
    assert (
        await client.put("/api/v1/notification-preferences", json={"channel": "email", "enabled": True})
    ).status_code == 401
