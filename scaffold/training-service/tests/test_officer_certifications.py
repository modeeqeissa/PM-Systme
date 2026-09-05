import datetime as dt
import uuid

from sqlalchemy import select

from app.models import OfficerCertification
from tests.conftest import SessionLocal


async def _set_expires_date(officer_cert_id, expires_date: dt.date) -> None:
    """Simulate time passing: back-date expires_date directly in the DB (the
    API never lets a client set it, so tests reach past it to exercise
    recompute)."""
    async with SessionLocal() as session:
        row = await session.get(OfficerCertification, officer_cert_id)
        row.expires_date = expires_date
        await session.commit()


async def test_issue_computes_expires_date_from_course_validity(
    client, auth_train, make_course, make_certification
):
    course = await make_course(validity_months=12)
    cert = await make_certification(course=course)
    officer_id = str(uuid.uuid4())

    r = await client.post(
        "/api/v1/officer-certifications",
        json={
            "officer_id": officer_id,
            "certification_id": cert.id,
            "issued_date": "2026-01-15",
        },
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["officer_id"] == officer_id
    assert body["issued_date"] == "2026-01-15"
    assert body["expires_date"] == "2027-01-15"
    assert body["status"] == "active"


async def test_issue_defaults_issued_date_to_today(
    client, auth_train, make_certification, today
):
    cert = await make_certification()
    r = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    assert r.json()["issued_date"] == today.isoformat()


async def test_issue_expires_date_clamps_to_month_end(
    client, auth_train, make_course, make_certification
):
    """Jan 31 + 1 month -> Feb 28 (2026 is not a leap year), never Mar 3."""
    course = await make_course(validity_months=1)
    cert = await make_certification(course=course)
    r = await client.post(
        "/api/v1/officer-certifications",
        json={
            "officer_id": str(uuid.uuid4()),
            "certification_id": cert.id,
            "issued_date": "2026-01-31",
        },
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    assert r.json()["expires_date"] == "2026-02-28"


async def test_issue_already_expired_computes_expired_status(
    client, auth_train, make_course, make_certification
):
    course = await make_course(validity_months=1)
    cert = await make_certification(course=course)
    r = await client.post(
        "/api/v1/officer-certifications",
        json={
            "officer_id": str(uuid.uuid4()),
            "certification_id": cert.id,
            "issued_date": "2020-01-01",
        },
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "expired"


async def test_issue_unknown_certification_404(client, auth_train):
    r = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": 999999},
        headers=auth_train,
    )
    assert r.status_code == 404


async def test_issue_requires_training_cert_write(client, auth_none, make_certification):
    cert = await make_certification()
    r = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_list_filter_by_officer_and_status(client, auth_train, make_certification):
    cert = await make_certification()
    officer_a = str(uuid.uuid4())
    officer_b = str(uuid.uuid4())
    await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": officer_a, "certification_id": cert.id},
        headers=auth_train,
    )
    await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": officer_b, "certification_id": cert.id},
        headers=auth_train,
    )

    r = await client.get(
        "/api/v1/officer-certifications", params={"officer_id": officer_a}, headers=auth_train
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["officer_id"] == officer_a

    r = await client.get(
        "/api/v1/officer-certifications", params={"status": "active"}, headers=auth_train
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_get_unknown_officer_certification_404(client, auth_train):
    r = await client.get(
        f"/api/v1/officer-certifications/{uuid.uuid4()}", headers=auth_train
    )
    assert r.status_code == 404


async def test_officer_certifications_require_auth(client):
    r = await client.get("/api/v1/officer-certifications")
    assert r.status_code == 401


# --- FR-TRAIN-03: expiry recompute ------------------------------------------
async def test_recompute_flags_expiring_soon_and_expired(
    client, auth_train, make_certification, today
):
    cert = await make_certification()
    r1 = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    r2 = await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    soon_id, expired_id = r1.json()["id"], r2.json()["id"]
    # Both issued as "active" just now; back-date their expires_date to
    # simulate time passing without a new issuance.
    await _set_expires_date(soon_id, today + dt.timedelta(days=5))
    await _set_expires_date(expired_id, today - dt.timedelta(days=1))

    r = await client.post("/api/v1/officer-certifications/recompute-status", headers=auth_train)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert body["checked"] >= 2

    r = await client.get(f"/api/v1/officer-certifications/{soon_id}", headers=auth_train)
    assert r.json()["status"] == "expiring_soon"
    r = await client.get(f"/api/v1/officer-certifications/{expired_id}", headers=auth_train)
    assert r.json()["status"] == "expired"


async def test_recompute_no_changes_returns_zero_updated(client, auth_train, make_certification):
    cert = await make_certification()
    await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    r = await client.post("/api/v1/officer-certifications/recompute-status", headers=auth_train)
    assert r.status_code == 200
    assert r.json()["updated"] == 0


async def test_recompute_requires_training_cert_write(client, auth_none):
    r = await client.post("/api/v1/officer-certifications/recompute-status", headers=auth_none)
    assert r.status_code == 403
