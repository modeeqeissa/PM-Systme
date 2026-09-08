"""awards — commendations, the positive counterpart to discipline_records
(docs §9.3.6 revised)."""
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


async def test_record_and_list_awards(client, auth_hr, make_officer):
    officer = await make_officer()
    approver = await make_officer(rank="Superintendent")
    r = await client.post(
        f"/api/v1/officers/{officer.id}/awards",
        json={
            "title": "Commendation for Bravery",
            "description": "Entered a burning building to rescue two residents.",
            "awarded_date": "2026-08-15",
            "awarded_by": str(approver.id),
        },
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["officer_id"] == str(officer.id)
    assert body["title"] == "Commendation for Bravery"
    assert body["awarded_by"] == str(approver.id)
    aid = body["id"]

    got = await client.get(f"/api/v1/awards/{aid}", headers=auth_hr)
    assert got.status_code == 200 and got.json()["awarded_date"] == "2026-08-15"

    listed = await client.get(f"/api/v1/officers/{officer.id}/awards", headers=auth_hr)
    assert [a["id"] for a in listed.json()] == [aid]

    evs = await _events("AwardRecorded")
    assert len(evs) == 1
    assert evs[0].body["payload"]["title"] == "Commendation for Bravery"


async def test_award_without_awarded_by(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/awards",
        json={"title": "Long Service Medal", "awarded_date": "2026-01-01"},
        headers=auth_hr,
    )
    assert r.status_code == 201
    assert r.json()["awarded_by"] is None


async def test_award_unknown_officer_404(client, auth_hr):
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/awards",
        json={"title": "X", "awarded_date": "2026-01-01"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_award_unknown_awarded_by_404(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/awards",
        json={"title": "X", "awarded_date": "2026-01-01", "awarded_by": str(uuid.uuid4())},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_award_get_404(client, auth_hr):
    r = await client.get(f"/api/v1/awards/{uuid.uuid4()}", headers=auth_hr)
    assert r.status_code == 404


async def test_award_write_requires_hr_award_write(client, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/awards",
        json={"title": "X", "awarded_date": "2026-01-01"},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_award_read_requires_hr_award_read(client, auth_none, make_officer):
    officer = await make_officer()
    r = await client.get(f"/api/v1/officers/{officer.id}/awards", headers=auth_none)
    assert r.status_code == 403
