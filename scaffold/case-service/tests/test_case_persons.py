"""case_persons — link/unlink a person to a case with a role (docs §9.3.2)."""
import uuid

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


async def test_link_person_to_case_201_and_event(client, make_case, make_person, auth_rw):
    case = await make_case(status="investigating")
    person = await make_person()
    r = await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "witness"},
        headers=auth_rw,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert set(data) == {"id", "case_id", "person_id", "role"}
    assert data["case_id"] == str(case.id)
    assert data["person_id"] == str(person.id)
    assert data["role"] == "witness"

    evs = await _events("PersonLinkedToCase")
    assert len(evs) == 1
    assert evs[0].body["payload"]["role"] == "witness"


async def test_link_is_idempotent_on_triple(client, make_case, make_person, auth_rw):
    case = await make_case()
    person = await make_person()
    body = {"person_id": str(person.id), "role": "suspect"}
    first = await client.post(f"/api/v1/cases/{case.id}/persons", json=body, headers=auth_rw)
    assert first.status_code == 201
    again = await client.post(f"/api/v1/cases/{case.id}/persons", json=body, headers=auth_rw)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert len(await _events("PersonLinkedToCase")) == 1


async def test_same_person_two_roles_on_one_case(client, make_case, make_person, auth_rw):
    case = await make_case()
    person = await make_person()
    r1 = await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "suspect"},
        headers=auth_rw,
    )
    r2 = await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "witness"},
        headers=auth_rw,
    )
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]

    listing = await client.get(f"/api/v1/cases/{case.id}/persons", headers=auth_rw)
    assert {row["role"] for row in listing.json()} == {"suspect", "witness"}


async def test_same_person_across_two_cases_different_roles(client, make_case, make_person, auth_rw):
    person = await make_person()
    c1 = await make_case()
    c2 = await make_case()
    await client.post(
        f"/api/v1/cases/{c1.id}/persons",
        json={"person_id": str(person.id), "role": "victim"},
        headers=auth_rw,
    )
    await client.post(
        f"/api/v1/cases/{c2.id}/persons",
        json={"person_id": str(person.id), "role": "suspect"},
        headers=auth_rw,
    )
    l1 = await client.get(f"/api/v1/cases/{c1.id}/persons", headers=auth_rw)
    l2 = await client.get(f"/api/v1/cases/{c2.id}/persons", headers=auth_rw)
    assert l1.json()[0]["role"] == "victim"
    assert l2.json()[0]["role"] == "suspect"


async def test_link_unknown_case_404(client, make_person, auth_rw):
    person = await make_person()
    r = await client.post(
        f"/api/v1/cases/{uuid.uuid4()}/persons",
        json={"person_id": str(person.id), "role": "witness"},
        headers=auth_rw,
    )
    assert r.status_code == 404


async def test_link_unknown_person_404(client, make_case, auth_rw):
    case = await make_case()
    r = await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(uuid.uuid4()), "role": "witness"},
        headers=auth_rw,
    )
    assert r.status_code == 404
    assert "person" in r.json()["detail"].lower()


async def test_link_bad_role_422(client, make_case, make_person, auth_rw):
    case = await make_case()
    person = await make_person()
    r = await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "informant"},
        headers=auth_rw,
    )
    assert r.status_code == 422


async def test_link_requires_write(client, make_case, make_person, auth_ro):
    case = await make_case()
    person = await make_person()
    r = await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "witness"},
        headers=auth_ro,
    )
    assert r.status_code == 403


async def test_list_case_persons_requires_read(client, make_case, auth_none):
    case = await make_case()
    r = await client.get(f"/api/v1/cases/{case.id}/persons", headers=auth_none)
    assert r.status_code == 403


async def test_list_case_persons_unknown_case_404(client, auth_rw):
    r = await client.get(f"/api/v1/cases/{uuid.uuid4()}/persons", headers=auth_rw)
    assert r.status_code == 404


async def test_unlink_one_role_leaves_the_other(client, make_case, make_person, auth_rw):
    case = await make_case()
    person = await make_person()
    for role in ("suspect", "witness"):
        await client.post(
            f"/api/v1/cases/{case.id}/persons",
            json={"person_id": str(person.id), "role": role},
            headers=auth_rw,
        )

    r = await client.delete(
        f"/api/v1/cases/{case.id}/persons/{person.id}?role=suspect", headers=auth_rw
    )
    assert r.status_code == 204

    remaining = await client.get(f"/api/v1/cases/{case.id}/persons", headers=auth_rw)
    assert [row["role"] for row in remaining.json()] == ["witness"]

    evs = await _events("PersonUnlinkedFromCase")
    assert len(evs) == 1 and evs[0].body["payload"]["roles"] == ["suspect"]


async def test_unlink_all_roles_when_role_omitted(client, make_case, make_person, auth_rw):
    case = await make_case()
    person = await make_person()
    for role in ("suspect", "witness"):
        await client.post(
            f"/api/v1/cases/{case.id}/persons",
            json={"person_id": str(person.id), "role": role},
            headers=auth_rw,
        )

    r = await client.delete(f"/api/v1/cases/{case.id}/persons/{person.id}", headers=auth_rw)
    assert r.status_code == 204

    remaining = await client.get(f"/api/v1/cases/{case.id}/persons", headers=auth_rw)
    assert remaining.json() == []

    evs = await _events("PersonUnlinkedFromCase")
    assert len(evs) == 1 and evs[0].body["payload"]["roles"] == ["suspect", "witness"]


async def test_unlink_nonexistent_link_404(client, make_case, make_person, auth_rw):
    case = await make_case()
    person = await make_person()
    r = await client.delete(f"/api/v1/cases/{case.id}/persons/{person.id}", headers=auth_rw)
    assert r.status_code == 404


async def test_unlink_requires_write(client, make_case, make_person, auth_rw, auth_ro):
    case = await make_case()
    person = await make_person()
    await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "witness"},
        headers=auth_rw,
    )
    r = await client.delete(f"/api/v1/cases/{case.id}/persons/{person.id}", headers=auth_ro)
    assert r.status_code == 403


async def test_unlink_then_person_delete_succeeds(client, make_case, make_person, auth_rw, auth_ro):
    """After the last link is removed, the person can be deleted (no refs left)."""
    case = await make_case()
    person = await make_person()
    await client.post(
        f"/api/v1/cases/{case.id}/persons",
        json={"person_id": str(person.id), "role": "witness"},
        headers=auth_rw,
    )
    blocked = await client.delete(f"/api/v1/persons/{person.id}", headers=auth_ro)
    assert blocked.status_code == 409

    await client.delete(f"/api/v1/cases/{case.id}/persons/{person.id}", headers=auth_rw)
    ok = await client.delete(f"/api/v1/persons/{person.id}", headers=auth_ro)
    assert ok.status_code == 204
