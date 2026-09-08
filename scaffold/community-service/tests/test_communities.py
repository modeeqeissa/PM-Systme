"""communities + organizations — docs §9.3.4 (revised)."""
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


# --- communities ------------------------------------------------------
async def test_create_and_get_community(client, auth_comm):
    station = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/communities",
        json={"name": "Riverside Watch", "station_id": station, "description": "East bank"},
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"id", "name", "station_id", "description"}
    assert body["name"] == "Riverside Watch"
    assert body["station_id"] == station

    got = await client.get(f"/api/v1/communities/{body['id']}", headers=auth_comm)
    assert got.status_code == 200 and got.json()["description"] == "East bank"

    evs = await _events("CommunityCreated")
    assert len(evs) == 1 and evs[0].body["payload"]["community_id"] == body["id"]


async def test_create_community_requires_write(client, auth_none):
    r = await client.post(
        "/api/v1/communities",
        json={"name": "X", "station_id": str(uuid.uuid4())},
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_list_communities_filtered_by_station(client, make_community, auth_comm):
    s1, s2 = uuid.uuid4(), uuid.uuid4()
    await make_community(name="A", station_id=s1)
    await make_community(name="B", station_id=s2)
    r = await client.get(f"/api/v1/communities?station_id={s1}", headers=auth_comm)
    assert r.status_code == 200
    assert [c["name"] for c in r.json()] == ["A"]


async def test_patch_community_name_not_station(client, make_community, auth_comm):
    c = await make_community(name="Old")
    r = await client.patch(
        f"/api/v1/communities/{c.id}", json={"name": "New", "description": "d"}, headers=auth_comm
    )
    assert r.status_code == 200
    assert r.json()["name"] == "New"
    assert r.json()["station_id"] == str(c.station_id)  # unchanged
    evs = await _events("CommunityUpdated")
    assert evs[0].body["payload"]["changed_fields"] == ["description", "name"]


async def test_patch_community_404(client, auth_comm):
    r = await client.patch(
        f"/api/v1/communities/{uuid.uuid4()}", json={"name": "N"}, headers=auth_comm
    )
    assert r.status_code == 404


# --- organizations ----------------------------------------------------
async def test_create_organization_standalone_and_linked(client, make_community, auth_comm):
    free = await client.post(
        "/api/v1/organizations", json={"name": "Free NGO"}, headers=auth_comm
    )
    assert free.status_code == 201
    assert free.json()["community_id"] is None

    c = await make_community()
    linked = await client.post(
        "/api/v1/organizations",
        json={"name": "Ward Assoc", "community_id": str(c.id), "contact_name": "Ada", "contact_phone": "123"},
        headers=auth_comm,
    )
    assert linked.status_code == 201
    assert linked.json()["community_id"] == str(c.id)
    assert linked.json()["contact_name"] == "Ada"

    evs = await _events("OrganizationCreated")
    assert len(evs) == 2


async def test_create_organization_unknown_community_404(client, auth_comm):
    r = await client.post(
        "/api/v1/organizations",
        json={"name": "Ghost", "community_id": str(uuid.uuid4())},
        headers=auth_comm,
    )
    assert r.status_code == 404


async def test_list_organizations_by_community(client, make_community, auth_comm):
    c = await make_community()
    await client.post(
        "/api/v1/organizations", json={"name": "In", "community_id": str(c.id)}, headers=auth_comm
    )
    await client.post("/api/v1/organizations", json={"name": "Out"}, headers=auth_comm)
    r = await client.get(f"/api/v1/organizations?community_id={c.id}", headers=auth_comm)
    assert [o["name"] for o in r.json()] == ["In"]


async def test_patch_organization_relink_and_404_on_bad_community(client, make_community, auth_comm):
    c1 = await make_community(name="C1")
    c2 = await make_community(name="C2")
    org = (await client.post(
        "/api/v1/organizations", json={"name": "Org", "community_id": str(c1.id)}, headers=auth_comm
    )).json()

    ok = await client.patch(
        f"/api/v1/organizations/{org['id']}", json={"community_id": str(c2.id)}, headers=auth_comm
    )
    assert ok.status_code == 200 and ok.json()["community_id"] == str(c2.id)

    bad = await client.patch(
        f"/api/v1/organizations/{org['id']}",
        json={"community_id": str(uuid.uuid4())},
        headers=auth_comm,
    )
    assert bad.status_code == 404


async def test_organization_read_requires_community_read(client, auth_none):
    r = await client.get("/api/v1/organizations", headers=auth_none)
    assert r.status_code == 403
