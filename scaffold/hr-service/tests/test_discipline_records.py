"""FR-HR-06 CRUD + the confidentiality/RBAC restriction (docs Section 2.3:
discipline is HR/command-only). auth_cmd (Station Commander) is a real,
non-HR role seeded with plenty of *other* HR permissions (hr.transfer.*,
hr.leave.*) — proving it still can't reach discipline data is the actual
test of the restriction, not just checking a token with zero permissions.
"""
import uuid

_BASE = {"incident_date": "2026-08-15", "description": "Late for shift without notice."}


async def test_create_discipline_record(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records",
        json={**_BASE, "outcome": "Verbal warning", "confidentiality_level": "restricted"},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["incident_date"] == "2026-08-15"
    assert body["description"] == "Late for shift without notice."
    assert body["outcome"] == "Verbal warning"
    assert body["confidentiality_level"] == "restricted"


async def test_create_discipline_record_defaults_confidentiality_level(
    client, auth_hr, make_officer
):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )
    assert r.status_code == 201, r.text
    assert r.json()["confidentiality_level"] == "restricted"
    assert r.json()["outcome"] is None


async def test_create_discipline_record_missing_required_fields_422(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json={}, headers=auth_hr
    )
    assert r.status_code == 422


async def test_create_discipline_record_unknown_officer_404(client, auth_hr):
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/discipline-records", json=_BASE, headers=auth_hr
    )
    assert r.status_code == 404


async def test_get_update_delete_discipline_record(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records",
        json={**_BASE, "confidentiality_level": "restricted"},
        headers=auth_hr,
    )
    record_id = r.json()["id"]

    r = await client.get(f"/api/v1/discipline-records/{record_id}", headers=auth_hr)
    assert r.status_code == 200
    assert r.json()["id"] == record_id

    r = await client.patch(
        f"/api/v1/discipline-records/{record_id}",
        json={"confidentiality_level": "confidential", "outcome": "Written reprimand"},
        headers=auth_hr,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["confidentiality_level"] == "confidential"
    assert body["outcome"] == "Written reprimand"
    assert body["description"] == _BASE["description"]  # untouched fields survive

    r = await client.delete(f"/api/v1/discipline-records/{record_id}", headers=auth_hr)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/discipline-records/{record_id}", headers=auth_hr)
    assert r.status_code == 404


async def test_officer_discipline_history(client, auth_hr, make_officer):
    officer = await make_officer()
    await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )
    await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )

    r = await client.get(
        f"/api/v1/officers/{officer.id}/discipline-records", headers=auth_hr
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_get_unknown_discipline_record_404(client, auth_hr):
    r = await client.get(f"/api/v1/discipline-records/{uuid.uuid4()}", headers=auth_hr)
    assert r.status_code == 404


async def test_patch_unknown_discipline_record_404(client, auth_hr):
    r = await client.patch(
        f"/api/v1/discipline-records/{uuid.uuid4()}",
        json={"confidentiality_level": "confidential"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_delete_unknown_discipline_record_404(client, auth_hr):
    r = await client.delete(f"/api/v1/discipline-records/{uuid.uuid4()}", headers=auth_hr)
    assert r.status_code == 404


# --- the confidentiality restriction itself ---------------------------------
async def test_station_commander_cannot_list_discipline_records(
    client, auth_hr, auth_cmd, make_officer
):
    officer = await make_officer()
    await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )

    r = await client.get(
        f"/api/v1/officers/{officer.id}/discipline-records", headers=auth_cmd
    )
    assert r.status_code == 403


async def test_station_commander_cannot_read_single_discipline_record(
    client, auth_hr, auth_cmd, make_officer
):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )
    record_id = r.json()["id"]

    r = await client.get(f"/api/v1/discipline-records/{record_id}", headers=auth_cmd)
    assert r.status_code == 403


async def test_station_commander_cannot_create_discipline_record(
    client, auth_cmd, make_officer
):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_cmd
    )
    assert r.status_code == 403


async def test_station_commander_cannot_update_or_delete_discipline_record(
    client, auth_hr, auth_cmd, make_officer
):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )
    record_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/discipline-records/{record_id}",
        json={"confidentiality_level": "confidential"},
        headers=auth_cmd,
    )
    assert r.status_code == 403

    r = await client.delete(f"/api/v1/discipline-records/{record_id}", headers=auth_cmd)
    assert r.status_code == 403

    # untouched — still readable/present via the permitted role
    r = await client.get(f"/api/v1/discipline-records/{record_id}", headers=auth_hr)
    assert r.status_code == 200
    assert r.json()["confidentiality_level"] == "restricted"


async def test_no_permission_token_cannot_read_discipline_records(
    client, auth_hr, auth_none, make_officer
):
    officer = await make_officer()
    await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records", json=_BASE, headers=auth_hr
    )

    r = await client.get(
        f"/api/v1/officers/{officer.id}/discipline-records", headers=auth_none
    )
    assert r.status_code == 403


async def test_discipline_records_require_auth(client):
    r = await client.get(f"/api/v1/discipline-records/{uuid.uuid4()}")
    assert r.status_code == 401
