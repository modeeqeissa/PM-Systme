"""Person master records — CRUD + search (docs §9.3.2 revised).

Tokens (see conftest): E2E-RW = case.read + case.write (Patrol Officer),
E2E-RO = case.read + case.approve (Station Commander), E2E-NONE = neither.
So create/update need `auth_rw`; delete needs `auth_ro` (case.approve).
"""
import uuid

import pytest
from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal


async def _events(event_type: str) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        return list(
            (
                await s.scalars(
                    select(OutboxEvent).where(OutboxEvent.event_type == event_type)
                )
            ).all()
        )


def _body(**over):
    b = {"first_name": "Amina", "last_name": "Diallo"}
    b.update(over)
    return b


# --- create -------------------------------------------------------------
async def test_create_person_201_and_shape(client, auth_rw):
    r = await client.post("/api/v1/persons", json=_body(national_id="NID-100"), headers=auth_rw)
    assert r.status_code == 201, r.text
    data = r.json()
    assert set(data) == {
        "id", "first_name", "last_name", "date_of_birth", "national_id",
        "gender", "address", "phone", "notes", "created_at",
    }
    assert data["first_name"] == "Amina"
    assert data["national_id"] == "NID-100"
    uuid.UUID(data["id"])

    evs = await _events("PersonCreated")
    assert len(evs) == 1
    assert evs[0].body["payload"]["person_id"] == data["id"]
    assert evs[0].body["payload"]["national_id"] == "NID-100"


async def test_create_person_requires_write(client, auth_ro):
    r = await client.post("/api/v1/persons", json=_body(), headers=auth_ro)
    assert r.status_code == 403


async def test_create_person_401_without_token(client):
    r = await client.post("/api/v1/persons", json=_body())
    assert r.status_code == 401


async def test_create_person_missing_name_422(client, auth_rw):
    r = await client.post("/api/v1/persons", json={"first_name": "Solo"}, headers=auth_rw)
    assert r.status_code == 422


async def test_duplicate_national_id_409(client, auth_rw):
    r1 = await client.post("/api/v1/persons", json=_body(national_id="NID-DUP"), headers=auth_rw)
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/persons", json=_body(first_name="Other", national_id="NID-DUP"), headers=auth_rw
    )
    assert r2.status_code == 409


async def test_multiple_persons_without_national_id_allowed(client, auth_rw):
    r1 = await client.post("/api/v1/persons", json=_body(), headers=auth_rw)
    r2 = await client.post("/api/v1/persons", json=_body(first_name="Bob"), headers=auth_rw)
    assert r1.status_code == r2.status_code == 201


# --- search -----------------------------------------------------------
async def test_search_by_name_case_insensitive_substring(client, make_person, auth_rw):
    await make_person(first_name="Kwame", last_name="Mensah")
    await make_person(first_name="Yaa", last_name="Asantewaa")
    r = await client.get("/api/v1/persons?q=MENS", headers=auth_rw)
    assert r.status_code == 200
    names = {p["last_name"] for p in r.json()}
    assert names == {"Mensah"}


async def test_search_by_national_id_exact(client, make_person, auth_ro):
    await make_person(national_id="NID-EXACT-1")
    await make_person(national_id="NID-EXACT-2")
    r = await client.get("/api/v1/persons?national_id=NID-EXACT-1", headers=auth_ro)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1 and body[0]["national_id"] == "NID-EXACT-1"


async def test_search_no_filter_returns_recent(client, make_person, auth_rw):
    for i in range(3):
        await make_person(last_name=f"Recent{i}")
    r = await client.get("/api/v1/persons", headers=auth_rw)
    assert r.status_code == 200
    assert len(r.json()) == 3


async def test_search_requires_read(client, auth_none):
    r = await client.get("/api/v1/persons", headers=auth_none)
    assert r.status_code == 403


# --- get ------------------------------------------------------------
async def test_get_person_200_and_404(client, make_person, auth_ro):
    p = await make_person()
    ok = await client.get(f"/api/v1/persons/{p.id}", headers=auth_ro)
    assert ok.status_code == 200 and ok.json()["id"] == str(p.id)

    missing = await client.get(f"/api/v1/persons/{uuid.uuid4()}", headers=auth_ro)
    assert missing.status_code == 404


# --- update -------------------------------------------------------------
async def test_patch_person_partial_update_and_event(client, make_person, auth_rw):
    p = await make_person(first_name="Old", last_name="Name", phone="111")
    r = await client.patch(
        f"/api/v1/persons/{p.id}", json={"phone": "222", "notes": "known alias: Ghost"}, headers=auth_rw
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["phone"] == "222"
    assert data["notes"] == "known alias: Ghost"
    assert data["first_name"] == "Old"  # untouched

    evs = await _events("PersonUpdated")
    assert len(evs) == 1
    assert evs[0].body["payload"]["changed_fields"] == ["notes", "phone"]


async def test_patch_person_404(client, auth_rw):
    r = await client.patch(f"/api/v1/persons/{uuid.uuid4()}", json={"phone": "9"}, headers=auth_rw)
    assert r.status_code == 404


async def test_patch_person_requires_write(client, make_person, auth_ro):
    p = await make_person()
    r = await client.patch(f"/api/v1/persons/{p.id}", json={"phone": "9"}, headers=auth_ro)
    assert r.status_code == 403


async def test_patch_duplicate_national_id_409(client, make_person, auth_rw):
    await make_person(national_id="NID-A")
    p2 = await make_person(national_id="NID-B")
    r = await client.patch(
        f"/api/v1/persons/{p2.id}", json={"national_id": "NID-A"}, headers=auth_rw
    )
    assert r.status_code == 409


async def test_patch_empty_body_is_noop(client, make_person, auth_rw):
    p = await make_person()
    r = await client.patch(f"/api/v1/persons/{p.id}", json={}, headers=auth_rw)
    assert r.status_code == 200
    assert await _events("PersonUpdated") == []


# --- delete -------------------------------------------------------------
async def test_delete_person_204_and_event(client, make_person, auth_ro):
    p = await make_person()
    r = await client.delete(f"/api/v1/persons/{p.id}", headers=auth_ro)
    assert r.status_code == 204

    gone = await client.get(f"/api/v1/persons/{p.id}", headers=auth_ro)
    assert gone.status_code == 404

    evs = await _events("PersonDeleted")
    assert len(evs) == 1 and evs[0].body["payload"]["person_id"] == str(p.id)


async def test_delete_person_requires_approve_not_write(client, make_person, auth_rw):
    p = await make_person()
    r = await client.delete(f"/api/v1/persons/{p.id}", headers=auth_rw)
    assert r.status_code == 403


async def test_delete_person_404(client, auth_ro):
    r = await client.delete(f"/api/v1/persons/{uuid.uuid4()}", headers=auth_ro)
    assert r.status_code == 404


async def test_delete_person_blocked_while_referenced_by_arrest(
    client, make_case, make_person, auth_rw, auth_ro
):
    case = await make_case(status="investigating")
    suspect = await make_person()
    rec = await client.post(
        f"/api/v1/cases/{case.id}/arrests",
        json={
            "officer_id": str(uuid.uuid4()),
            "suspect_id": str(suspect.id),
            "arrest_date": "2026-09-03T12:00:00+00:00",
        },
        headers=auth_rw,
    )
    assert rec.status_code == 201

    r = await client.delete(f"/api/v1/persons/{suspect.id}", headers=auth_ro)
    assert r.status_code == 409
    assert "arrests=1" in r.json()["detail"]
