import uuid


async def test_request_transfer(client, auth_hr, make_officer, make_unit):
    officer = await make_officer()
    to_unit = await make_unit(name="Cyber Crime")
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["from_unit_id"] == str(officer.unit_id)
    assert body["to_unit_id"] == str(to_unit.id)
    assert body["requested_at"] is not None  # docs Section 9.3.6: set at request time
    assert body["effective_date"] is None
    assert body["approved_by"] is None


async def test_request_transfer_unknown_officer_404(client, auth_hr, make_unit):
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_request_transfer_unknown_unit_404(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(uuid.uuid4())},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_request_transfer_requires_hr_transfer_write(
    client, auth_cmd, make_officer, make_unit
):
    """Station Commander approves transfers but doesn't file them."""
    officer = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_officer_transfer_history_and_global_queue(
    client, auth_hr, make_officer, make_unit
):
    officer = await make_officer()
    to_unit = await make_unit()
    await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )

    r = await client.get(f"/api/v1/officers/{officer.id}/transfers", headers=auth_hr)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = await client.get("/api/v1/transfers", params={"status": "pending"}, headers=auth_hr)
    assert r.status_code == 200
    assert any(t["officer_id"] == str(officer.id) for t in r.json())


async def test_approve_transfer_moves_officer_and_updates_assignment(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    approver = await make_officer(rank="Inspector")
    to_unit = await make_unit(name="Traffic")
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_cmd,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == str(approver.id)
    assert body["effective_date"] == "2026-10-01"

    r = await client.get(f"/api/v1/officers/{officer.id}", headers=auth_hr)
    assert r.json()["unit_id"] == str(to_unit.id)

    r = await client.get(f"/api/v1/officers/{officer.id}/assignments", headers=auth_hr)
    newest = r.json()[0]
    assert newest["unit_id"] == str(to_unit.id)
    assert newest["start_date"] == "2026-10-01"  # effective_date drives the new assignment


async def test_approve_transfer_missing_approved_by_or_effective_date_422(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    approver = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}", json={"status": "approved"}, headers=auth_cmd
    )
    assert r.status_code == 422

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={"status": "approved", "approved_by": str(approver.id)},
        headers=auth_cmd,
    )
    assert r.status_code == 422  # effective_date still missing


async def test_approve_transfer_unknown_approved_by_404(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(uuid.uuid4()),
            "effective_date": "2026-10-01",
        },
        headers=auth_cmd,
    )
    assert r.status_code == 404


async def test_reject_transfer_leaves_officer_unit_and_approval_fields_unchanged(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    to_unit = await make_unit()
    original_unit_id = str(officer.unit_id)
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}", json={"status": "rejected"}, headers=auth_cmd
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    # docs Section 9.3.6: approved_by/effective_date are "set on approval" —
    # a rejection leaves both null, even though the body didn't error for
    # omitting them (only approval requires them).
    assert body["approved_by"] is None
    assert body["effective_date"] is None

    r = await client.get(f"/api/v1/officers/{officer.id}", headers=auth_hr)
    assert r.json()["unit_id"] == original_unit_id


async def test_decide_already_decided_transfer_409(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    approver = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]
    await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_cmd,
    )

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}", json={"status": "rejected"}, headers=auth_cmd
    )
    assert r.status_code == 409


async def test_decide_unknown_transfer_404(client, auth_cmd, make_officer):
    approver = await make_officer()
    r = await client.patch(
        f"/api/v1/transfers/{uuid.uuid4()}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_cmd,
    )
    assert r.status_code == 404


async def test_hr_officer_role_also_holds_transfer_approve(
    client, auth_hr, make_officer, make_unit
):
    """"HR Officer / Admin: Full CRUD on HR domain" (docs Section 2.3) includes
    hr.transfer.approve, not just hr.transfer.write."""
    officer = await make_officer()
    approver = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_hr,
    )
    # HR Officer DOES hold hr.transfer.approve (full HR CRUD) -> succeeds.
    assert r.status_code == 200


async def test_decide_transfer_forbidden_without_approve_permission(
    client, auth_none, auth_hr, make_officer, make_unit
):
    officer = await make_officer()
    approver = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_transfers_require_auth(client):
    r = await client.get("/api/v1/transfers")
    assert r.status_code == 401
