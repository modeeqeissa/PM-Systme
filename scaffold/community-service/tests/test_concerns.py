import uuid


async def test_log_concern_independent_of_meeting(client, auth_comm):
    r = await client.post(
        "/api/v1/concerns", json={"category": "traffic"}, headers=auth_comm
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["meeting_id"] is None
    assert body["category"] == "traffic"
    assert body["status"] == "open"


async def test_log_concern_linked_to_meeting(client, auth_comm, make_meeting):
    meeting = await make_meeting()
    r = await client.post(
        "/api/v1/concerns",
        json={"meeting_id": str(meeting.id), "category": "corruption"},
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    assert r.json()["meeting_id"] == str(meeting.id)


async def test_log_concern_unknown_meeting_404(client, auth_comm):
    r = await client.post(
        "/api/v1/concerns",
        json={"meeting_id": str(uuid.uuid4()), "category": "safety"},
        headers=auth_comm,
    )
    assert r.status_code == 404


async def test_log_concern_requires_community_write(client, auth_none):
    r = await client.post(
        "/api/v1/concerns", json={"category": "safety"}, headers=auth_none
    )
    assert r.status_code == 403


async def test_list_concerns_filters(client, auth_comm, make_concern):
    await make_concern(category="safety")
    await make_concern(category="traffic", status="resolved")

    r = await client.get(
        "/api/v1/concerns", params={"category": "safety"}, headers=auth_comm
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = await client.get(
        "/api/v1/concerns", params={"status": "resolved"}, headers=auth_comm
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["category"] == "traffic"


async def test_get_unknown_concern_404(client, auth_comm):
    r = await client.get(f"/api/v1/concerns/{uuid.uuid4()}", headers=auth_comm)
    assert r.status_code == 404


async def test_update_concern_status(client, auth_comm, make_concern):
    concern = await make_concern()
    r = await client.patch(
        f"/api/v1/concerns/{concern.id}",
        json={"status": "in_progress"},
        headers=auth_comm,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    r = await client.patch(
        f"/api/v1/concerns/{concern.id}", json={"status": "resolved"}, headers=auth_comm
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"


async def test_update_unknown_concern_404(client, auth_comm):
    r = await client.patch(
        f"/api/v1/concerns/{uuid.uuid4()}", json={"status": "resolved"}, headers=auth_comm
    )
    assert r.status_code == 404


async def test_update_concern_status_requires_community_write(client, auth_none, make_concern):
    concern = await make_concern()
    r = await client.patch(
        f"/api/v1/concerns/{concern.id}", json={"status": "resolved"}, headers=auth_none
    )
    assert r.status_code == 403


async def test_concerns_require_auth(client):
    r = await client.get("/api/v1/concerns")
    assert r.status_code == 401
