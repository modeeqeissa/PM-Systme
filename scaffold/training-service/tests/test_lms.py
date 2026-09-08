"""LMS additions — materials, sessions, attendance, assessments (docs §9.3.5).

auth_train = "Training Officer" (training.cert.read + write); auth_none = neither.
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


# --- materials -------------------------------------------------------
async def test_material_upload_get_delete(client, make_course, auth_train):
    course = await make_course()
    up = await client.post(
        f"/api/v1/courses/{course.id}/materials",
        data={"title": "Slide deck"},
        files={"file": ("deck.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth_train,
    )
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["course_id"] == course.id
    assert body["title"] == "Slide deck"
    assert body["file_ref"].startswith("mat_")
    mid = body["id"]

    listed = await client.get(f"/api/v1/courses/{course.id}/materials", headers=auth_train)
    assert [m["id"] for m in listed.json()] == [mid]

    got = await client.get(f"/api/v1/materials/{mid}", headers=auth_train)
    assert got.status_code == 200

    gone = await client.delete(f"/api/v1/materials/{mid}", headers=auth_train)
    assert gone.status_code == 204
    assert (await client.get(f"/api/v1/materials/{mid}", headers=auth_train)).status_code == 404

    assert len(await _events("MaterialAdded")) == 1
    assert len(await _events("MaterialRemoved")) == 1


async def test_material_upload_unknown_course_404(client, auth_train):
    r = await client.post(
        "/api/v1/courses/999999/materials",
        data={"title": "x"},
        files={"file": ("x.txt", b"x", "text/plain")},
        headers=auth_train,
    )
    assert r.status_code == 404


async def test_material_upload_requires_write(client, make_course, auth_none):
    course = await make_course()
    r = await client.post(
        f"/api/v1/courses/{course.id}/materials",
        data={"title": "x"},
        files={"file": ("x.txt", b"x", "text/plain")},
        headers=auth_none,
    )
    assert r.status_code == 403


# --- sessions + attendance ------------------------------------------
async def test_schedule_session_and_list(client, make_course, auth_train):
    course = await make_course()
    r = await client.post(
        "/api/v1/sessions",
        json={
            "course_id": course.id,
            "scheduled_at": "2026-11-02T09:00:00+00:00",
            "location": "Room 4",
            "capacity": 20,
        },
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    assert r.json()["course_id"] == course.id
    assert r.json()["capacity"] == 20

    listed = await client.get(f"/api/v1/sessions?course_id={course.id}", headers=auth_train)
    assert [s["id"] for s in listed.json()] == [r.json()["id"]]
    assert len(await _events("SessionScheduled")) == 1


async def test_schedule_session_unknown_course_404(client, auth_train):
    r = await client.post(
        "/api/v1/sessions",
        json={"course_id": 999999, "scheduled_at": "2026-11-02T09:00:00+00:00"},
        headers=auth_train,
    )
    assert r.status_code == 404


async def test_patch_session(client, make_session, auth_train):
    s = await make_session()
    r = await client.patch(
        f"/api/v1/sessions/{s.id}",
        json={"location": "Moved to Hall A", "capacity": 50},
        headers=auth_train,
    )
    assert r.status_code == 200
    assert r.json()["location"] == "Moved to Hall A"
    assert r.json()["capacity"] == 50
    assert (await _events("SessionUpdated"))[0].body["payload"]["changed_fields"] == ["capacity", "location"]


async def test_attendance_register_dedupe_and_status(client, make_session, auth_train):
    s = await make_session()
    officer = str(uuid.uuid4())

    reg = await client.post(
        f"/api/v1/sessions/{s.id}/attendance",
        json={"officer_id": officer},
        headers=auth_train,
    )
    assert reg.status_code == 201
    assert reg.json()["status"] == "registered"
    aid = reg.json()["id"]

    dup = await client.post(
        f"/api/v1/sessions/{s.id}/attendance",
        json={"officer_id": officer},
        headers=auth_train,
    )
    assert dup.status_code == 409

    moved = await client.patch(
        f"/api/v1/attendance/{aid}", json={"status": "attended"}, headers=auth_train
    )
    assert moved.status_code == 200 and moved.json()["status"] == "attended"

    listed = await client.get(f"/api/v1/sessions/{s.id}/attendance", headers=auth_train)
    assert listed.json()[0]["status"] == "attended"

    assert len(await _events("AttendanceRecorded")) == 1
    chg = await _events("AttendanceStatusChanged")
    assert chg[0].body["payload"]["to_status"] == "attended"


async def test_attendance_unknown_session_404(client, auth_train):
    r = await client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/attendance",
        json={"officer_id": str(uuid.uuid4())},
        headers=auth_train,
    )
    assert r.status_code == 404


# --- assessments + results ----------------------------------------
async def test_assessment_and_pass_fail_grading(client, make_course, auth_train):
    course = await make_course()
    a = await client.post(
        f"/api/v1/courses/{course.id}/assessments",
        json={"title": "Written test", "passing_score": 70},
        headers=auth_train,
    )
    assert a.status_code == 201, a.text
    aid = a.json()["id"]
    assert a.json()["course_id"] == course.id

    fail = await client.post(
        f"/api/v1/assessments/{aid}/results",
        json={"officer_id": str(uuid.uuid4()), "score": 55},
        headers=auth_train,
    )
    assert fail.status_code == 201
    assert fail.json()["passed"] is False

    passed = await client.post(
        f"/api/v1/assessments/{aid}/results",
        json={"officer_id": str(uuid.uuid4()), "score": 88.5},
        headers=auth_train,
    )
    assert passed.status_code == 201
    assert passed.json()["passed"] is True
    assert passed.json()["taken_at"]

    results = await client.get(f"/api/v1/assessments/{aid}/results", headers=auth_train)
    assert len(results.json()) == 2

    assert len(await _events("AssessmentCreated")) == 1
    recs = await _events("AssessmentResultRecorded")
    assert {r.body["payload"]["passed"] for r in recs} == {True, False}
    assert recs[0].body["payload"]["course_id"] == course.id


async def test_grading_uses_passing_score_at_time_of_grading(client, make_assessment, auth_train):
    """A later change to passing_score does not rewrite an already-graded result."""
    a = await make_assessment(passing_score=60)
    officer = str(uuid.uuid4())
    r1 = await client.post(
        f"/api/v1/assessments/{a.id}/results",
        json={"officer_id": officer, "score": 65},
        headers=auth_train,
    )
    assert r1.json()["passed"] is True

    # raise the bar directly (assessments have no PATCH endpoint by design)
    async with SessionLocal() as s:
        from app.models import Assessment

        row = await s.get(Assessment, a.id)
        row.passing_score = 90
        await s.commit()

    still = await client.get(f"/api/v1/assessments/{a.id}/results", headers=auth_train)
    assert still.json()[0]["passed"] is True  # unchanged


async def test_assessment_result_unknown_assessment_404(client, auth_train):
    r = await client.post(
        f"/api/v1/assessments/{uuid.uuid4()}/results",
        json={"officer_id": str(uuid.uuid4()), "score": 50},
        headers=auth_train,
    )
    assert r.status_code == 404


async def test_assessment_read_requires_training_read(client, make_course, auth_none):
    course = await make_course()
    r = await client.get(f"/api/v1/courses/{course.id}/assessments", headers=auth_none)
    assert r.status_code == 403


async def test_session_and_material_reads_401_without_token(client, make_session):
    s = await make_session()
    assert (await client.get(f"/api/v1/sessions/{s.id}")).status_code == 401
