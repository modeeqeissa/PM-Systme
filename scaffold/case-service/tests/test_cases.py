"""GET /api/v1/cases/{id} and PATCH /api/v1/cases/{id}/status (FR-CASE-03).

Tokens come from iam-service's real login/MFA flow (see conftest):
E2E-RW = case.read + case.write, E2E-RO = case.read only, E2E-NONE = neither.
"""
import uuid

import pytest


async def test_get_case_returns_contract_shape(client, make_case, auth_ro):
    case = await make_case(status="open")
    r = await client.get(f"/api/v1/cases/{case.id}", headers=auth_ro)
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {
        "id", "case_number", "incident_id", "status",
        "lead_officer_id", "opened_at", "closed_at",
    }
    assert data["id"] == str(case.id)
    assert data["status"] == "open"
    assert data["closed_at"] is None


async def test_get_case_404_when_missing(client, auth_ro):
    r = await client.get(f"/api/v1/cases/{uuid.uuid4()}", headers=auth_ro)
    assert r.status_code == 404


async def test_get_case_403_without_read_permission(client, make_case, auth_none):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}", headers=auth_none)
    assert r.status_code == 403


async def test_get_case_401_without_token(client, make_case):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}")
    assert r.status_code == 401


@pytest.mark.parametrize(
    "start,target",
    [
        ("open", "investigating"),
        ("open", "suspended"),
        ("open", "closed"),
        ("investigating", "referred_prosecution"),
        ("investigating", "closed"),
        ("referred_prosecution", "investigating"),
        ("suspended", "investigating"),
        ("suspended", "open"),
    ],
)
async def test_valid_status_transitions_return_200(client, make_case, auth_rw, start, target):
    case = await make_case(status=start)
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": target}, headers=auth_rw
    )
    assert r.status_code == 200
    assert r.json()["status"] == target


async def test_transition_to_closed_sets_closed_at(client, make_case, auth_rw):
    case = await make_case(status="investigating")
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": "closed"}, headers=auth_rw
    )
    assert r.status_code == 200
    assert r.json()["closed_at"] is not None


@pytest.mark.parametrize(
    "start,target",
    [
        ("open", "referred_prosecution"),
        ("closed", "investigating"),
        ("closed", "open"),
        ("investigating", "open"),
        ("referred_prosecution", "suspended"),
        ("open", "open"),
    ],
)
async def test_invalid_status_transitions_return_409(client, make_case, auth_rw, start, target):
    case = await make_case(status=start)
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": target}, headers=auth_rw
    )
    assert r.status_code == 409


async def test_status_patch_rejects_unknown_status_value(client, make_case, auth_rw):
    case = await make_case(status="open")
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": "archived"}, headers=auth_rw
    )
    assert r.status_code == 422


async def test_status_patch_404_when_missing(client, auth_rw):
    r = await client.patch(
        f"/api/v1/cases/{uuid.uuid4()}/status", json={"status": "closed"}, headers=auth_rw
    )
    assert r.status_code == 404


async def test_status_patch_403_without_write_permission(client, make_case, auth_ro):
    case = await make_case(status="open")
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": "closed"}, headers=auth_ro
    )
    assert r.status_code == 403


async def test_status_patch_persists(client, make_case, auth_rw):
    case = await make_case(status="open")
    await client.patch(
        f"/api/v1/cases/{case.id}/status", json={"status": "investigating"}, headers=auth_rw
    )
    r = await client.get(f"/api/v1/cases/{case.id}", headers=auth_rw)
    assert r.json()["status"] == "investigating"


# --- POST /cases (FR-CASE-02) ------------------------------------------------
async def test_open_case_assigns_sequential_number(client, auth_rw):
    r1 = await client.post(
        "/api/v1/cases", json={"lead_officer_id": str(uuid.uuid4())}, headers=auth_rw
    )
    r2 = await client.post(
        "/api/v1/cases", json={"lead_officer_id": str(uuid.uuid4())}, headers=auth_rw
    )
    assert r1.status_code == r2.status_code == 201
    n1 = int(r1.json()["case_number"].rsplit("-", 1)[1])
    n2 = int(r2.json()["case_number"].rsplit("-", 1)[1])
    assert n2 == n1 + 1
    assert r1.json()["status"] == "open"
    assert r1.json()["closed_at"] is None


async def test_open_case_from_unknown_incident_404(client, auth_rw):
    r = await client.post(
        "/api/v1/cases",
        json={"lead_officer_id": str(uuid.uuid4()), "incident_id": str(uuid.uuid4())},
        headers=auth_rw,
    )
    assert r.status_code == 404


async def test_open_case_requires_write(client, auth_ro):
    r = await client.post(
        "/api/v1/cases", json={"lead_officer_id": str(uuid.uuid4())}, headers=auth_ro
    )
    assert r.status_code == 403


async def test_open_case_links_incident(client, auth_rw):
    inc = await client.post(
        "/api/v1/incidents",
        json={
            "reported_by": str(uuid.uuid4()),
            "incident_type": "assault",
            "description": "x",
            "station_id": str(uuid.uuid4()),
            "reported_at": "2026-09-03T08:00:00+00:00",
        },
        headers={**auth_rw, "Idempotency-Key": str(uuid.uuid4())},
    )
    incident_id = inc.json()["id"]
    r = await client.post(
        "/api/v1/cases",
        json={"lead_officer_id": str(uuid.uuid4()), "incident_id": incident_id},
        headers=auth_rw,
    )
    assert r.status_code == 201
    assert r.json()["incident_id"] == incident_id


# --- POST /cases/{id}/arrests ---------------------------------------------
async def test_record_arrest(client, make_case, auth_rw):
    case = await make_case(status="investigating")
    r = await client.post(
        f"/api/v1/cases/{case.id}/arrests",
        json={
            "officer_id": str(uuid.uuid4()),
            "suspect_id": str(uuid.uuid4()),
            "arrest_date": "2026-09-03T12:00:00+00:00",
            "legal_basis": "caught in the act",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["case_id"] == str(case.id)
    assert body["legal_basis"] == "caught in the act"
    uuid.UUID(body["id"])


async def test_record_arrest_unknown_case_404(client, auth_rw):
    r = await client.post(
        f"/api/v1/cases/{uuid.uuid4()}/arrests",
        json={
            "officer_id": str(uuid.uuid4()),
            "suspect_id": str(uuid.uuid4()),
            "arrest_date": "2026-09-03T12:00:00+00:00",
        },
        headers=auth_rw,
    )
    assert r.status_code == 404


async def test_record_arrest_requires_write(client, make_case, auth_ro):
    case = await make_case()
    r = await client.post(
        f"/api/v1/cases/{case.id}/arrests",
        json={
            "officer_id": str(uuid.uuid4()),
            "suspect_id": str(uuid.uuid4()),
            "arrest_date": "2026-09-03T12:00:00+00:00",
        },
        headers=auth_ro,
    )
    assert r.status_code == 403


# --- GET /cases/{id}/arrests ------------------------------------------------
async def test_list_arrests(client, make_case, auth_rw):
    case = await make_case(status="investigating")
    suspect_id = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/cases/{case.id}/arrests",
        json={
            "officer_id": str(uuid.uuid4()),
            "suspect_id": suspect_id,
            "arrest_date": "2026-09-03T12:00:00+00:00",
            "location": "Central Market",
            "legal_basis": "caught in the act",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text

    r = await client.get(f"/api/v1/cases/{case.id}/arrests", headers=auth_rw)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["case_id"] == str(case.id)
    assert body[0]["suspect_id"] == suspect_id
    assert body[0]["location"] == "Central Market"


async def test_list_arrests_unknown_case_404(client, auth_rw):
    r = await client.get(f"/api/v1/cases/{uuid.uuid4()}/arrests", headers=auth_rw)
    assert r.status_code == 404


async def test_list_arrests_requires_read(client, make_case, auth_none):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}/arrests", headers=auth_none)
    assert r.status_code == 403


# --- POST/GET /cases/{id}/statements (FR-CASE-05) --------------------------
async def test_record_statement(client, make_case, auth_rw):
    case = await make_case(status="investigating")
    recorded_by = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/cases/{case.id}/statements",
        json={
            "recorded_by": recorded_by,
            "party_type": "witness",
            "statement_text": "I saw the suspect leave through the back door.",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["case_id"] == str(case.id)
    assert body["recorded_by"] == recorded_by
    assert body["party_type"] == "witness"
    uuid.UUID(body["id"])


async def test_record_statement_unknown_case_404(client, auth_rw):
    r = await client.post(
        f"/api/v1/cases/{uuid.uuid4()}/statements",
        json={
            "recorded_by": str(uuid.uuid4()),
            "party_type": "victim",
            "statement_text": "It happened around midnight.",
        },
        headers=auth_rw,
    )
    assert r.status_code == 404


async def test_record_statement_requires_write(client, make_case, auth_ro):
    case = await make_case()
    r = await client.post(
        f"/api/v1/cases/{case.id}/statements",
        json={
            "recorded_by": str(uuid.uuid4()),
            "party_type": "suspect",
            "statement_text": "I wasn't there.",
        },
        headers=auth_ro,
    )
    assert r.status_code == 403


async def test_list_statements(client, make_case, auth_rw):
    case = await make_case(status="investigating")
    recorded_by = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/cases/{case.id}/statements",
        json={
            "recorded_by": recorded_by,
            "party_type": "victim",
            "statement_text": "My wallet was taken from my bag.",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text

    r = await client.get(f"/api/v1/cases/{case.id}/statements", headers=auth_rw)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["case_id"] == str(case.id)
    assert body[0]["recorded_by"] == recorded_by
    assert body[0]["party_type"] == "victim"
    assert body[0]["statement_text"] == "My wallet was taken from my bag."


async def test_list_statements_unknown_case_404(client, auth_rw):
    r = await client.get(f"/api/v1/cases/{uuid.uuid4()}/statements", headers=auth_rw)
    assert r.status_code == 404


async def test_list_statements_requires_read(client, make_case, auth_none):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}/statements", headers=auth_none)
    assert r.status_code == 403


# --- POST/GET /cases/{id}/court-proceedings (FR-CASE-06) -------------------
async def test_record_court_proceeding(client, make_case, auth_rw):
    case = await make_case(status="referred_prosecution")
    r = await client.post(
        f"/api/v1/cases/{case.id}/court-proceedings",
        json={
            "hearing_date": "2026-10-01T09:00:00+00:00",
            "court_name": "Central Magistrates Court",
            "notes": "First hearing, plea entered.",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["case_id"] == str(case.id)
    assert body["court_name"] == "Central Magistrates Court"
    assert body["verdict"] is None
    uuid.UUID(body["id"])


async def test_record_court_proceeding_unknown_case_404(client, auth_rw):
    r = await client.post(
        f"/api/v1/cases/{uuid.uuid4()}/court-proceedings",
        json={"hearing_date": "2026-10-01T09:00:00+00:00"},
        headers=auth_rw,
    )
    assert r.status_code == 404


async def test_record_court_proceeding_requires_write(client, make_case, auth_ro):
    case = await make_case()
    r = await client.post(
        f"/api/v1/cases/{case.id}/court-proceedings",
        json={"hearing_date": "2026-10-01T09:00:00+00:00"},
        headers=auth_ro,
    )
    assert r.status_code == 403


async def test_list_court_proceedings(client, make_case, auth_rw):
    case = await make_case(status="referred_prosecution")
    r = await client.post(
        f"/api/v1/cases/{case.id}/court-proceedings",
        json={
            "hearing_date": "2026-10-01T09:00:00+00:00",
            "court_name": "Central Magistrates Court",
            "verdict": "guilty",
        },
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text

    r = await client.get(f"/api/v1/cases/{case.id}/court-proceedings", headers=auth_rw)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["case_id"] == str(case.id)
    assert body[0]["court_name"] == "Central Magistrates Court"
    assert body[0]["verdict"] == "guilty"


async def test_list_court_proceedings_unknown_case_404(client, auth_rw):
    r = await client.get(f"/api/v1/cases/{uuid.uuid4()}/court-proceedings", headers=auth_rw)
    assert r.status_code == 404


async def test_list_court_proceedings_requires_read(client, make_case, auth_none):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}/court-proceedings", headers=auth_none)
    assert r.status_code == 403


# --- POST/GET/DELETE /cases/{id}/officers (FR-CASE-07) --------------------
# E2E-RO = Station Commander (case.read + case.approve) -> may assign officers.
# E2E-RW = Patrol Officer (case.read + case.write, NO case.approve) -> may not.
async def test_assign_case_officer(client, make_case, auth_ro):
    case = await make_case(status="investigating")
    officer_id = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/cases/{case.id}/officers",
        json={"officer_id": officer_id, "role_on_case": "forensic liaison"},
        headers=auth_ro,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body == {
        "case_id": str(case.id),
        "officer_id": officer_id,
        "role_on_case": "forensic liaison",
    }


async def test_reassign_existing_officer_updates_role_and_returns_200(
    client, make_case, auth_ro
):
    case = await make_case(status="investigating")
    officer_id = str(uuid.uuid4())
    first = await client.post(
        f"/api/v1/cases/{case.id}/officers",
        json={"officer_id": officer_id, "role_on_case": "support"},
        headers=auth_ro,
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/cases/{case.id}/officers",
        json={"officer_id": officer_id, "role_on_case": "lead"},
        headers=auth_ro,
    )
    assert second.status_code == 200, second.text
    assert second.json()["role_on_case"] == "lead"

    listing = await client.get(f"/api/v1/cases/{case.id}/officers", headers=auth_ro)
    assert [o["role_on_case"] for o in listing.json()] == ["lead"]  # not duplicated


async def test_assign_case_officer_unknown_case_404(client, auth_ro):
    r = await client.post(
        f"/api/v1/cases/{uuid.uuid4()}/officers",
        json={"officer_id": str(uuid.uuid4()), "role_on_case": "support"},
        headers=auth_ro,
    )
    assert r.status_code == 404


async def test_assign_case_officer_requires_approve_not_write(client, make_case, auth_rw):
    case = await make_case()
    r = await client.post(
        f"/api/v1/cases/{case.id}/officers",
        json={"officer_id": str(uuid.uuid4()), "role_on_case": "support"},
        headers=auth_rw,
    )
    assert r.status_code == 403


async def test_assign_case_officer_rejects_blank_role(client, make_case, auth_ro):
    case = await make_case()
    r = await client.post(
        f"/api/v1/cases/{case.id}/officers",
        json={"officer_id": str(uuid.uuid4()), "role_on_case": ""},
        headers=auth_ro,
    )
    assert r.status_code == 422


async def test_list_case_officers(client, make_case, auth_ro):
    case = await make_case(status="investigating")
    for role in ("lead", "support"):
        r = await client.post(
            f"/api/v1/cases/{case.id}/officers",
            json={"officer_id": str(uuid.uuid4()), "role_on_case": role},
            headers=auth_ro,
        )
        assert r.status_code == 201, r.text

    r = await client.get(f"/api/v1/cases/{case.id}/officers", headers=auth_ro)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert {o["role_on_case"] for o in body} == {"lead", "support"}
    assert all(o["case_id"] == str(case.id) for o in body)


async def test_list_case_officers_unknown_case_404(client, auth_ro):
    r = await client.get(f"/api/v1/cases/{uuid.uuid4()}/officers", headers=auth_ro)
    assert r.status_code == 404


async def test_list_case_officers_requires_read(client, make_case, auth_none):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}/officers", headers=auth_none)
    assert r.status_code == 403


async def test_unassign_case_officer(client, make_case, auth_ro):
    case = await make_case(status="investigating")
    officer_id = str(uuid.uuid4())
    await client.post(
        f"/api/v1/cases/{case.id}/officers",
        json={"officer_id": officer_id, "role_on_case": "support"},
        headers=auth_ro,
    )
    r = await client.delete(
        f"/api/v1/cases/{case.id}/officers/{officer_id}", headers=auth_ro
    )
    assert r.status_code == 204
    listing = await client.get(f"/api/v1/cases/{case.id}/officers", headers=auth_ro)
    assert listing.json() == []


async def test_unassign_case_officer_not_assigned_404(client, make_case, auth_ro):
    case = await make_case()
    r = await client.delete(
        f"/api/v1/cases/{case.id}/officers/{uuid.uuid4()}", headers=auth_ro
    )
    assert r.status_code == 404


async def test_unassign_case_officer_unknown_case_404(client, auth_ro):
    r = await client.delete(
        f"/api/v1/cases/{uuid.uuid4()}/officers/{uuid.uuid4()}", headers=auth_ro
    )
    assert r.status_code == 404


async def test_unassign_case_officer_requires_approve(client, make_case, auth_rw):
    case = await make_case()
    r = await client.delete(
        f"/api/v1/cases/{case.id}/officers/{uuid.uuid4()}", headers=auth_rw
    )
    assert r.status_code == 403


# --- GET /cases (list, FR-CASE-03 + FR-IAM-04 scope) -----------------------
def _sub(token: str) -> str:
    import jwt

    return jwt.decode(token, options={"verify_signature": False})["sub"]


async def test_list_requires_case_read(client, auth_none):
    r = await client.get("/api/v1/cases", headers=auth_none)
    assert r.status_code == 403


async def test_list_unauthenticated_401(client):
    assert (await client.get("/api/v1/cases")).status_code == 401


async def test_list_scopes_to_lead_officer_without_wide_permission(
    client, make_case, auth_rw, token_rw
):
    mine = await make_case(status="open", lead_officer_id=uuid.UUID(_sub(token_rw)))
    await make_case(status="open")  # someone else's
    await make_case(status="open")

    r = await client.get("/api/v1/cases", headers=auth_rw)
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert ids == [str(mine.id)]  # Patrol Officer sees only the case they lead


async def test_list_wide_scope_sees_all(client, make_case, auth_ro):
    for _ in range(3):
        await make_case(status="open")
    r = await client.get("/api/v1/cases", headers=auth_ro)
    assert r.status_code == 200
    assert len(r.json()) == 3  # Station Commander (case.approve) sees every case


async def test_list_status_filter_and_shape(client, make_case, auth_ro):
    await make_case(status="open")
    closed = await make_case(status="closed")
    r = await client.get("/api/v1/cases?status=closed", headers=auth_ro)
    assert [c["id"] for c in r.json()] == [str(closed.id)]
    row = r.json()[0]
    assert set(row) == {
        "id", "case_number", "incident_id", "status",
        "lead_officer_id", "opened_at", "closed_at",
    }


async def test_list_pagination(client, make_case, auth_ro):
    for _ in range(5):
        await make_case(status="open")
    page = await client.get("/api/v1/cases?limit=2&offset=0", headers=auth_ro)
    assert len(page.json()) == 2
    rest = await client.get("/api/v1/cases?limit=2&offset=4", headers=auth_ro)
    assert len(rest.json()) == 1
