import uuid


async def test_create_and_list_units(client, auth_hr):
    station_id = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/units",
        json={"name": "Central Patrol", "station_id": station_id},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Central Patrol"
    uuid.UUID(body["id"])

    r = await client.get("/api/v1/units", params={"station_id": station_id}, headers=auth_hr)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Central Patrol"


async def test_create_unit_requires_hr_unit_write(client, auth_cmd):
    r = await client.post(
        "/api/v1/units",
        json={"name": "Central Patrol", "station_id": str(uuid.uuid4())},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_list_units_requires_auth(client):
    r = await client.get("/api/v1/units")
    assert r.status_code == 401
