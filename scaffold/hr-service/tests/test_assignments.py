import uuid


async def test_record_assignment_closes_previous_and_updates_officer(
    client, auth_hr, make_officer, make_unit
):
    officer = await make_officer()
    new_unit = await make_unit(name="K9 Unit")

    r = await client.post(
        f"/api/v1/officers/{officer.id}/assignments",
        json={"unit_id": str(new_unit.id), "start_date": "2022-06-01"},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    assert r.json()["unit_id"] == str(new_unit.id)
    assert r.json()["end_date"] is None

    r = await client.get(f"/api/v1/officers/{officer.id}/assignments", headers=auth_hr)
    history = r.json()
    assert len(history) == 2  # the initial one from make_officer's implicit unit + this one
    newest, oldest = history[0], history[1]
    assert newest["unit_id"] == str(new_unit.id)
    assert oldest["end_date"] == "2022-06-01"  # closed by the new one starting

    r = await client.get(f"/api/v1/officers/{officer.id}", headers=auth_hr)
    assert r.json()["unit_id"] == str(new_unit.id)


async def test_record_assignment_unknown_officer_404(client, auth_hr, make_unit):
    unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/assignments",
        json={"unit_id": str(unit.id), "start_date": "2022-06-01"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_record_assignment_unknown_unit_404(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/assignments",
        json={"unit_id": str(uuid.uuid4()), "start_date": "2022-06-01"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_record_assignment_requires_hr_assignment_write(
    client, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/assignments",
        json={"unit_id": str(unit.id), "start_date": "2022-06-01"},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_list_assignments_unknown_officer_404(client, auth_hr):
    r = await client.get(f"/api/v1/officers/{uuid.uuid4()}/assignments", headers=auth_hr)
    assert r.status_code == 404
