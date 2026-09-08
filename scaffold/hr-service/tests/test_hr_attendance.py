"""hr_attendance — daily present/absent/late/excused (docs §9.3.6 revised).

auth_hr = "HR Officer" (all hr.* incl. hr.attendance.*); auth_cmd = "Station
Commander" (transfer/leave only — no hr.attendance.*); auth_none = neither.
"""
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


async def test_record_and_list_attendance(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/attendance",
        json={"date": "2026-09-01", "status": "present", "clock_in": "2026-09-01T08:02:00+00:00"},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["officer_id"] == str(officer.id)
    assert body["status"] == "present"
    assert body["date"] == "2026-09-01"

    await client.post(
        f"/api/v1/officers/{officer.id}/attendance",
        json={"date": "2026-09-02", "status": "late"},
        headers=auth_hr,
    )
    listed = await client.get(f"/api/v1/officers/{officer.id}/attendance", headers=auth_hr)
    assert [row["date"] for row in listed.json()] == ["2026-09-02", "2026-09-01"]  # newest first

    evs = await _events("HrAttendanceRecorded")
    assert len(evs) == 2


async def test_attendance_list_date_bounds(client, auth_hr, make_officer):
    officer = await make_officer()
    for d in ("2026-09-01", "2026-09-05", "2026-09-10"):
        await client.post(
            f"/api/v1/officers/{officer.id}/attendance",
            json={"date": d, "status": "present"},
            headers=auth_hr,
        )
    r = await client.get(
        f"/api/v1/officers/{officer.id}/attendance?from=2026-09-03&to=2026-09-08",
        headers=auth_hr,
    )
    assert [row["date"] for row in r.json()] == ["2026-09-05"]


async def test_attendance_duplicate_date_409(client, auth_hr, make_officer):
    officer = await make_officer()
    body = {"date": "2026-09-01", "status": "present"}
    first = await client.post(f"/api/v1/officers/{officer.id}/attendance", json=body, headers=auth_hr)
    assert first.status_code == 201
    dup = await client.post(f"/api/v1/officers/{officer.id}/attendance", json=body, headers=auth_hr)
    assert dup.status_code == 409


async def test_attendance_unknown_officer_404(client, auth_hr):
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/attendance",
        json={"date": "2026-09-01", "status": "present"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_attendance_bad_status_422(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/attendance",
        json={"date": "2026-09-01", "status": "on_leave"},
        headers=auth_hr,
    )
    assert r.status_code == 422


async def test_attendance_patch_status_and_clock_out(client, auth_hr, make_officer):
    officer = await make_officer()
    rec = await client.post(
        f"/api/v1/officers/{officer.id}/attendance",
        json={"date": "2026-09-01", "status": "present"},
        headers=auth_hr,
    )
    aid = rec.json()["id"]
    r = await client.patch(
        f"/api/v1/attendance/{aid}",
        json={"status": "excused", "clock_out": "2026-09-01T16:00:00+00:00"},
        headers=auth_hr,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "excused"
    assert r.json()["clock_out"] == "2026-09-01T16:00:00Z"
    assert sorted((await _events("HrAttendanceUpdated"))[0].body["payload"]["changed_fields"]) == [
        "clock_out",
        "status",
    ]


async def test_attendance_patch_404(client, auth_hr):
    r = await client.patch(
        f"/api/v1/attendance/{uuid.uuid4()}", json={"status": "absent"}, headers=auth_hr
    )
    assert r.status_code == 404


async def test_attendance_write_requires_hr_attendance_write(client, auth_cmd, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/attendance",
        json={"date": "2026-09-01", "status": "present"},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_attendance_read_401_without_token(client, make_officer):
    officer = await make_officer()
    r = await client.get(f"/api/v1/officers/{officer.id}/attendance")
    assert r.status_code == 401
