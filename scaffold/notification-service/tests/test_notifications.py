import uuid


async def test_list_own_notifications_only(
    client, auth_user1, auth_user2, user1_id, user2_id, make_notification
):
    await make_notification(recipient_user_id=uuid.UUID(user1_id), template_code="LEAVE_APPROVED")
    await make_notification(recipient_user_id=uuid.UUID(user2_id), template_code="LEAVE_REJECTED")

    r = await client.get("/api/v1/notifications", headers=auth_user1)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["template_code"] == "LEAVE_APPROVED"
    assert body[0]["recipient_user_id"] == user1_id


async def test_list_filter_by_status(client, auth_user1, user1_id, make_notification):
    await make_notification(recipient_user_id=uuid.UUID(user1_id), status="queued")
    await make_notification(recipient_user_id=uuid.UUID(user1_id), status="sent")

    r = await client.get(
        "/api/v1/notifications", params={"status": "sent"}, headers=auth_user1
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["status"] == "sent"


async def test_get_own_notification(client, auth_user1, user1_id, make_notification):
    n = await make_notification(recipient_user_id=uuid.UUID(user1_id))
    r = await client.get(f"/api/v1/notifications/{n.id}", headers=auth_user1)
    assert r.status_code == 200
    assert r.json()["id"] == n.id


async def test_cannot_get_someone_elses_notification_404(
    client, auth_user2, user1_id, make_notification
):
    n = await make_notification(recipient_user_id=uuid.UUID(user1_id))
    r = await client.get(f"/api/v1/notifications/{n.id}", headers=auth_user2)
    assert r.status_code == 404


async def test_get_unknown_notification_404(client, auth_user1):
    r = await client.get("/api/v1/notifications/999999999", headers=auth_user1)
    assert r.status_code == 404


async def test_notifications_require_auth(client):
    r = await client.get("/api/v1/notifications")
    assert r.status_code == 401
