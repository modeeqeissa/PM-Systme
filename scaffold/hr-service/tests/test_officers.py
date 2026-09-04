import uuid


async def test_create_officer_opens_first_assignment(client, auth_hr, make_unit):
    unit = await make_unit()
    body = {
        "user_id": str(uuid.uuid4()),
        "badge_number": "OFF-100",
        "rank": "Constable",
        "unit_id": str(unit.id),
        "hire_date": "2020-01-01",
    }
    r = await client.post("/api/v1/officers", json=body, headers=auth_hr)
    assert r.status_code == 201, r.text
    officer = r.json()
    assert officer["badge_number"] == "OFF-100"
    assert officer["status"] == "active"
    officer_id = officer["id"]

    r = await client.get(f"/api/v1/officers/{officer_id}/assignments", headers=auth_hr)
    assert r.status_code == 200
    assignments = r.json()
    assert len(assignments) == 1
    assert assignments[0]["unit_id"] == str(unit.id)
    assert assignments[0]["end_date"] is None


async def test_create_officer_unknown_unit_404(client, auth_hr):
    body = {
        "user_id": str(uuid.uuid4()),
        "badge_number": "OFF-101",
        "rank": "Constable",
        "unit_id": str(uuid.uuid4()),
        "hire_date": "2020-01-01",
    }
    r = await client.post("/api/v1/officers", json=body, headers=auth_hr)
    assert r.status_code == 404


async def test_create_officer_duplicate_badge_409(client, auth_hr, make_unit):
    unit = await make_unit()
    body = {
        "user_id": str(uuid.uuid4()),
        "badge_number": "OFF-DUP",
        "rank": "Constable",
        "unit_id": str(unit.id),
        "hire_date": "2020-01-01",
    }
    r1 = await client.post("/api/v1/officers", json=body, headers=auth_hr)
    assert r1.status_code == 201
    body2 = {**body, "user_id": str(uuid.uuid4())}
    r2 = await client.post("/api/v1/officers", json=body2, headers=auth_hr)
    assert r2.status_code == 409


async def test_create_officer_requires_hr_officer_write(client, auth_cmd, make_unit):
    unit = await make_unit()
    body = {
        "user_id": str(uuid.uuid4()),
        "badge_number": "OFF-102",
        "rank": "Constable",
        "unit_id": str(unit.id),
        "hire_date": "2020-01-01",
    }
    r = await client.post("/api/v1/officers", json=body, headers=auth_cmd)
    assert r.status_code == 403


async def test_get_and_list_officers(client, auth_hr, make_officer):
    officer = await make_officer(badge_number="OFF-200")
    r = await client.get(f"/api/v1/officers/{officer.id}", headers=auth_hr)
    assert r.status_code == 200
    assert r.json()["badge_number"] == "OFF-200"

    r = await client.get("/api/v1/officers", params={"unit_id": str(officer.unit_id)}, headers=auth_hr)
    assert r.status_code == 200
    assert any(o["id"] == str(officer.id) for o in r.json())


async def test_get_officer_unknown_404(client, auth_hr):
    r = await client.get(f"/api/v1/officers/{uuid.uuid4()}", headers=auth_hr)
    assert r.status_code == 404


async def test_patch_officer_status(client, auth_hr, make_officer):
    officer = await make_officer(status="active")
    r = await client.patch(
        f"/api/v1/officers/{officer.id}", json={"status": "suspended"}, headers=auth_hr
    )
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"


async def test_patch_officer_cannot_change_rank_or_unit(client, auth_hr, make_officer):
    """OfficerUpdate has no rank/unit_id fields — promotions/transfers own those."""
    officer = await make_officer(rank="Constable")
    r = await client.patch(
        f"/api/v1/officers/{officer.id}",
        json={"rank": "Inspector", "unit_id": str(uuid.uuid4())},
        headers=auth_hr,
    )
    # extra fields are silently ignored by the (extra-forbid-free) schema
    assert r.status_code == 200
    assert r.json()["rank"] == "Constable"


async def test_patch_officer_unknown_404(client, auth_hr):
    r = await client.patch(
        f"/api/v1/officers/{uuid.uuid4()}", json={"status": "retired"}, headers=auth_hr
    )
    assert r.status_code == 404


async def test_patch_officer_requires_hr_officer_write(client, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.patch(
        f"/api/v1/officers/{officer.id}", json={"status": "retired"}, headers=auth_cmd
    )
    assert r.status_code == 403


async def test_list_officers_requires_auth(client):
    r = await client.get("/api/v1/officers")
    assert r.status_code == 401
