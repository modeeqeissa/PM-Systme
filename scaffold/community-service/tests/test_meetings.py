import uuid


async def test_log_and_get_meeting(client, auth_comm):
    station_id = str(uuid.uuid4())
    facilitator_id = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": station_id,
            "facilitator_id": facilitator_id,
            "meeting_date": "2026-06-15",
            "location": "Community Hall",
        },
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["station_id"] == station_id
    assert body["facilitator_id"] == facilitator_id
    assert body["location"] == "Community Hall"

    r = await client.get(f"/api/v1/meetings/{body['id']}", headers=auth_comm)
    assert r.status_code == 200
    assert r.json()["meeting_date"] == "2026-06-15"


async def test_log_meeting_stores_attendee_summary(client, auth_comm):
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": str(uuid.uuid4()),
            "facilitator_id": str(uuid.uuid4()),
            "meeting_date": "2026-06-15",
            "location": "Community Hall",
            "attendee_summary": "~40 residents, ward councillor, 3 shopkeepers.",
        },
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    assert r.json()["attendee_summary"] == "~40 residents, ward councillor, 3 shopkeepers."

    r = await client.get(f"/api/v1/meetings/{r.json()['id']}", headers=auth_comm)
    assert r.json()["attendee_summary"] == "~40 residents, ward councillor, 3 shopkeepers."


async def test_log_meeting_requires_community_write(client, auth_none):
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": str(uuid.uuid4()),
            "facilitator_id": str(uuid.uuid4()),
            "meeting_date": "2026-06-15",
            "location": "Community Hall",
        },
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_list_meetings_filter_by_station(client, auth_comm, make_meeting):
    station_a = uuid.uuid4()
    station_b = uuid.uuid4()
    await make_meeting(station_id=station_a)
    await make_meeting(station_id=station_b)

    r = await client.get(
        "/api/v1/meetings", params={"station_id": str(station_a)}, headers=auth_comm
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["station_id"] == str(station_a)


async def test_get_unknown_meeting_404(client, auth_comm):
    r = await client.get(f"/api/v1/meetings/{uuid.uuid4()}", headers=auth_comm)
    assert r.status_code == 404


async def test_meetings_require_auth(client):
    r = await client.get("/api/v1/meetings")
    assert r.status_code == 401
