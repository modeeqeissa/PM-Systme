"""meeting_minutes (1:1) + decisions — docs §9.3.4 (revised)."""
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


# --- meeting_id on a meeting ------------------------------------------
async def test_log_meeting_with_community_id(client, make_community, auth_comm):
    c = await make_community()
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": str(c.station_id),
            "community_id": str(c.id),
            "facilitator_id": str(uuid.uuid4()),
            "meeting_date": "2026-07-01",
            "location": "Hall",
        },
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    assert r.json()["community_id"] == str(c.id)

    listed = await client.get(f"/api/v1/meetings?community_id={c.id}", headers=auth_comm)
    assert [m["id"] for m in listed.json()] == [r.json()["id"]]


async def test_log_meeting_unknown_community_404(client, auth_comm):
    r = await client.post(
        "/api/v1/meetings",
        json={
            "station_id": str(uuid.uuid4()),
            "community_id": str(uuid.uuid4()),
            "facilitator_id": str(uuid.uuid4()),
            "meeting_date": "2026-07-01",
            "location": "Hall",
        },
        headers=auth_comm,
    )
    assert r.status_code == 404


# --- minutes -------------------------------------------------------
async def test_minutes_create_get_edit(client, make_meeting, auth_comm):
    m = await make_meeting()
    recorder = str(uuid.uuid4())

    created = await client.post(
        f"/api/v1/meetings/{m.id}/minutes",
        json={"content": "Agenda: potholes. Decision: escalate to roads dept.", "recorded_by": recorder},
        headers=auth_comm,
    )
    assert created.status_code == 201, created.text
    assert created.json()["meeting_id"] == str(m.id)
    assert created.json()["recorded_by"] == recorder

    got = await client.get(f"/api/v1/meetings/{m.id}/minutes", headers=auth_comm)
    assert got.status_code == 200 and "potholes" in got.json()["content"]

    edited = await client.patch(
        f"/api/v1/meetings/{m.id}/minutes", json={"content": "Revised minutes."}, headers=auth_comm
    )
    assert edited.status_code == 200 and edited.json()["content"] == "Revised minutes."

    assert len(await _events("MeetingMinutesRecorded")) == 1
    assert len(await _events("MeetingMinutesUpdated")) == 1


async def test_minutes_second_create_409(client, make_meeting, auth_comm):
    m = await make_meeting()
    body = {"content": "first", "recorded_by": str(uuid.uuid4())}
    first = await client.post(f"/api/v1/meetings/{m.id}/minutes", json=body, headers=auth_comm)
    assert first.status_code == 201
    dup = await client.post(f"/api/v1/meetings/{m.id}/minutes", json=body, headers=auth_comm)
    assert dup.status_code == 409


async def test_minutes_unknown_meeting_404(client, auth_comm):
    r = await client.post(
        f"/api/v1/meetings/{uuid.uuid4()}/minutes",
        json={"content": "x", "recorded_by": str(uuid.uuid4())},
        headers=auth_comm,
    )
    assert r.status_code == 404


async def test_minutes_get_missing_404(client, make_meeting, auth_comm):
    m = await make_meeting()
    r = await client.get(f"/api/v1/meetings/{m.id}/minutes", headers=auth_comm)
    assert r.status_code == 404


async def test_minutes_create_requires_write(client, make_meeting, auth_none):
    m = await make_meeting()
    r = await client.post(
        f"/api/v1/meetings/{m.id}/minutes",
        json={"content": "x", "recorded_by": str(uuid.uuid4())},
        headers=auth_none,
    )
    assert r.status_code == 403


# --- decisions ---------------------------------------------------
async def test_decision_lifecycle(client, make_meeting, auth_comm):
    m = await make_meeting()
    rec = await client.post(
        f"/api/v1/meetings/{m.id}/decisions",
        json={"description": "Install speed bumps on Mill Lane."},
        headers=auth_comm,
    )
    assert rec.status_code == 201, rec.text
    did = rec.json()["id"]
    assert rec.json()["status"] == "pending"
    assert rec.json()["meeting_id"] == str(m.id)

    listed = await client.get(f"/api/v1/meetings/{m.id}/decisions", headers=auth_comm)
    assert [d["id"] for d in listed.json()] == [did]

    moved = await client.patch(
        f"/api/v1/decisions/{did}", json={"status": "implemented"}, headers=auth_comm
    )
    assert moved.status_code == 200 and moved.json()["status"] == "implemented"

    got = await client.get(f"/api/v1/decisions/{did}", headers=auth_comm)
    assert got.json()["status"] == "implemented"

    assert len(await _events("DecisionRecorded")) == 1
    chg = await _events("DecisionStatusChanged")
    assert chg[0].body["payload"]["from_status"] == "pending"
    assert chg[0].body["payload"]["to_status"] == "implemented"


async def test_decision_bad_status_422(client, make_meeting, auth_comm):
    m = await make_meeting()
    rec = await client.post(
        f"/api/v1/meetings/{m.id}/decisions", json={"description": "d"}, headers=auth_comm
    )
    r = await client.patch(
        f"/api/v1/decisions/{rec.json()['id']}", json={"status": "in_progress"}, headers=auth_comm
    )
    assert r.status_code == 422


async def test_decision_unknown_meeting_404(client, auth_comm):
    r = await client.post(
        f"/api/v1/meetings/{uuid.uuid4()}/decisions", json={"description": "d"}, headers=auth_comm
    )
    assert r.status_code == 404


async def test_decision_patch_404(client, auth_comm):
    r = await client.patch(
        f"/api/v1/decisions/{uuid.uuid4()}", json={"status": "abandoned"}, headers=auth_comm
    )
    assert r.status_code == 404


async def test_decision_read_requires_community_read(client, make_meeting, auth_none):
    m = await make_meeting()
    r = await client.get(f"/api/v1/meetings/{m.id}/decisions", headers=auth_none)
    assert r.status_code == 403
