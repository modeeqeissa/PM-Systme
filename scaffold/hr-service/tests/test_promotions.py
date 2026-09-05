import uuid


async def test_record_promotion_updates_officer_rank(client, auth_hr, make_officer):
    officer = await make_officer(rank="Constable")
    approver = await make_officer(rank="Inspector")
    r = await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={
            "new_rank": "Sergeant",
            "effective_date": "2026-10-01",
            "approved_by": str(approver.id),
        },
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["previous_rank"] == "Constable"
    assert body["new_rank"] == "Sergeant"
    assert body["effective_date"] == "2026-10-01"
    assert body["approved_by"] == str(approver.id)

    r = await client.get(f"/api/v1/officers/{officer.id}", headers=auth_hr)
    assert r.json()["rank"] == "Sergeant"


async def test_record_promotion_unknown_approved_by_404(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={
            "new_rank": "Sergeant",
            "effective_date": "2026-10-01",
            "approved_by": str(uuid.uuid4()),
        },
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_record_promotion_missing_required_fields_422(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={"new_rank": "Sergeant"},
        headers=auth_hr,
    )
    assert r.status_code == 422


async def test_promotion_history_newest_first(client, auth_hr, make_officer):
    officer = await make_officer(rank="Constable")
    approver = await make_officer()
    await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={
            "new_rank": "Sergeant",
            "effective_date": "2026-01-01",
            "approved_by": str(approver.id),
        },
        headers=auth_hr,
    )
    await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={
            "new_rank": "Inspector",
            "effective_date": "2026-06-01",
            "approved_by": str(approver.id),
        },
        headers=auth_hr,
    )

    r = await client.get(f"/api/v1/officers/{officer.id}/promotions", headers=auth_hr)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    assert history[0]["new_rank"] == "Inspector"
    assert history[0]["previous_rank"] == "Sergeant"
    assert history[1]["new_rank"] == "Sergeant"


async def test_record_promotion_unknown_officer_404(client, auth_hr, make_officer):
    approver = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/promotions",
        json={
            "new_rank": "Sergeant",
            "effective_date": "2026-10-01",
            "approved_by": str(approver.id),
        },
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_record_promotion_requires_hr_promotion_write(client, auth_cmd, make_officer):
    officer = await make_officer()
    approver = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={
            "new_rank": "Sergeant",
            "effective_date": "2026-10-01",
            "approved_by": str(approver.id),
        },
        headers=auth_cmd,
    )
    assert r.status_code == 403
