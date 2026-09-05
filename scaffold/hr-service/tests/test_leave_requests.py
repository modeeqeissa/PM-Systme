import uuid


async def test_request_leave(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "annual", "start_date": "2026-11-01", "end_date": "2026-11-10"},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["leave_type"] == "annual"
    assert body["start_date"] == "2026-11-01"
    assert body["end_date"] == "2026-11-10"
    assert body["approved_by"] is None


async def test_request_leave_end_before_start_422(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "annual", "start_date": "2026-11-10", "end_date": "2026-11-01"},
        headers=auth_hr,
    )
    assert r.status_code == 422


async def test_request_leave_unknown_officer_404(client, auth_hr):
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_request_leave_requires_hr_leave_write(client, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "annual", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_officer_leave_history_and_global_queue(client, auth_hr, auth_cmd, make_officer):
    officer = await make_officer()
    await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={
            "leave_type": "compassionate",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
        },
        headers=auth_hr,
    )

    r = await client.get(f"/api/v1/officers/{officer.id}/leave-requests", headers=auth_hr)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = await client.get("/api/v1/leave-requests", params={"status": "pending"}, headers=auth_cmd)
    assert r.status_code == 200
    assert any(lr["officer_id"] == str(officer.id) for lr in r.json())


async def test_station_commander_approves_leave(client, auth_hr, auth_cmd, make_officer):
    """Docs Section 2.3: Station Commander approves transfers/leave at station level."""
    officer = await make_officer()
    approver = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    leave_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/leave-requests/{leave_id}",
        json={"status": "approved", "approved_by": str(approver.id)},
        headers=auth_cmd,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == str(approver.id)


async def test_approve_leave_missing_approved_by_422(client, auth_hr, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    leave_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/leave-requests/{leave_id}", json={"status": "approved"}, headers=auth_cmd
    )
    assert r.status_code == 422


async def test_approve_leave_unknown_approved_by_404(client, auth_hr, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    leave_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/leave-requests/{leave_id}",
        json={"status": "approved", "approved_by": str(uuid.uuid4())},
        headers=auth_cmd,
    )
    assert r.status_code == 404


async def test_reject_leave_leaves_approved_by_null(client, auth_hr, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    leave_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/leave-requests/{leave_id}", json={"status": "rejected"}, headers=auth_cmd
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["approved_by"] is None


async def test_decide_already_decided_leave_409(client, auth_hr, auth_cmd, make_officer):
    officer = await make_officer()
    approver = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    leave_id = r.json()["id"]
    await client.patch(
        f"/api/v1/leave-requests/{leave_id}",
        json={"status": "approved", "approved_by": str(approver.id)},
        headers=auth_cmd,
    )

    r = await client.patch(
        f"/api/v1/leave-requests/{leave_id}", json={"status": "rejected"}, headers=auth_cmd
    )
    assert r.status_code == 409


async def test_decide_unknown_leave_request_404(client, auth_cmd, make_officer):
    approver = await make_officer()
    r = await client.patch(
        f"/api/v1/leave-requests/{uuid.uuid4()}",
        json={"status": "approved", "approved_by": str(approver.id)},
        headers=auth_cmd,
    )
    assert r.status_code == 404


async def test_decide_leave_forbidden_without_approve_permission(
    client, auth_none, auth_hr, make_officer
):
    officer = await make_officer()
    approver = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/leave-requests",
        json={"leave_type": "sick", "start_date": "2026-11-01", "end_date": "2026-11-02"},
        headers=auth_hr,
    )
    leave_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/leave-requests/{leave_id}",
        json={"status": "approved", "approved_by": str(approver.id)},
        headers=auth_none,
    )
    assert r.status_code == 403
