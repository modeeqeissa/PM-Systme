"""Transactional outbox: same-transaction enqueue + relay-to-Kafka (SRS §3.4)."""
import uuid

from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal


async def _outbox_rows(event_type: str | None = None) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        q = select(OutboxEvent).order_by(OutboxEvent.id)
        if event_type:
            q = q.where(OutboxEvent.event_type == event_type)
        return list((await s.scalars(q)).all())


async def test_officer_created_and_unit_created_enqueued(client, auth_hr, make_unit):
    unit = await make_unit()
    r = await client.post(
        "/api/v1/officers",
        json={
            "user_id": str(uuid.uuid4()),
            "badge_number": "OUTBOX-1",
            "rank": "Constable",
            "unit_id": str(unit.id),
            "hire_date": "2020-01-01",
        },
        headers=auth_hr,
    )
    officer_id = r.json()["id"]

    rows = await _outbox_rows("OfficerCreated")
    assert len(rows) == 1
    assert rows[0].aggregate_id == officer_id
    assert rows[0].topic.endswith("hr.officer_created")
    assert rows[0].body["payload"]["badge_number"] == "OUTBOX-1"
    assert rows[0].body["actor_id"] is not None  # came from the JWT


async def test_supervisor_changed_enqueues_on_create_and_patch(client, auth_hr, make_officer):
    supervisor = await make_officer(rank="Sergeant")
    officer = await make_officer()

    # set via PATCH
    await client.patch(
        f"/api/v1/officers/{officer.id}",
        json={"supervisor_id": str(supervisor.id)},
        headers=auth_hr,
    )
    rows = await _outbox_rows("OfficerSupervisorChanged")
    assert len(rows) == 1
    assert rows[0].topic.endswith("hr.officer_supervisor_changed")
    assert rows[0].body["payload"]["officer_id"] == str(officer.id)
    assert rows[0].body["payload"]["supervisor_id"] == str(supervisor.id)
    assert rows[0].body["payload"]["previous_supervisor_id"] is None

    # no-op PATCH (same supervisor) enqueues nothing new
    await client.patch(
        f"/api/v1/officers/{officer.id}",
        json={"supervisor_id": str(supervisor.id)},
        headers=auth_hr,
    )
    assert len(await _outbox_rows("OfficerSupervisorChanged")) == 1


async def test_supervisor_id_in_officer_created_payload(client, auth_hr, make_officer, make_unit):
    supervisor = await make_officer(rank="Inspector")
    unit = await make_unit()
    r = await client.post(
        "/api/v1/officers",
        json={
            "user_id": str(uuid.uuid4()),
            "badge_number": "OUTBOX-SUP",
            "rank": "Constable",
            "unit_id": str(unit.id),
            "hire_date": "2020-01-01",
            "supervisor_id": str(supervisor.id),
        },
        headers=auth_hr,
    )
    officer_id = r.json()["id"]
    created = await _outbox_rows("OfficerCreated")
    assert created[-1].body["payload"]["supervisor_id"] == str(supervisor.id)
    changed = await _outbox_rows("OfficerSupervisorChanged")
    assert any(c.body["payload"]["officer_id"] == officer_id for c in changed)


async def test_discipline_record_create_update_delete_all_enqueue(
    client, auth_hr, make_officer
):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/discipline-records",
        json={"incident_date": "2026-08-15", "description": "Late for shift."},
        headers=auth_hr,
    )
    record_id = r.json()["id"]
    await client.patch(
        f"/api/v1/discipline-records/{record_id}",
        json={"confidentiality_level": "confidential"},
        headers=auth_hr,
    )
    await client.delete(f"/api/v1/discipline-records/{record_id}", headers=auth_hr)

    created = await _outbox_rows("DisciplineRecordCreated")
    updated = await _outbox_rows("DisciplineRecordUpdated")
    deleted = await _outbox_rows("DisciplineRecordDeleted")
    assert len(created) == len(updated) == len(deleted) == 1
    assert created[0].aggregate_id == record_id
    assert updated[0].body["payload"]["confidentiality_level"] == "confidential"
    assert deleted[0].aggregate_id == record_id
    # the confidential narrative never reaches the (more widely-readable) audit
    # trail — only the fact-of-record does.
    assert "description" not in created[0].body["payload"]
    assert "description" not in updated[0].body["payload"]


async def test_transfer_requested_and_status_changed_enqueue(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    approver = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]
    await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_cmd,
    )

    requested = await _outbox_rows("TransferRequested")
    changed = await _outbox_rows("TransferStatusChanged")
    assert len(requested) == 1 and requested[0].aggregate_id == transfer_id
    assert len(changed) == 1
    assert changed[0].body["payload"]["from_status"] == "pending"
    assert changed[0].body["payload"]["to_status"] == "approved"
    assert changed[0].body["payload"]["approved_by"] == str(approver.id)
    assert changed[0].body["payload"]["effective_date"] == "2026-10-01"
    # actor on the approval event is the approving Station Commander, not HR
    assert "Station Commander" in (changed[0].body["actor_role"] or "")


async def test_failed_transfer_decision_writes_no_new_outbox_row(
    client, auth_hr, auth_cmd, make_officer, make_unit
):
    officer = await make_officer()
    approver = await make_officer()
    to_unit = await make_unit()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/transfers",
        json={"to_unit_id": str(to_unit.id)},
        headers=auth_hr,
    )
    transfer_id = r.json()["id"]
    await client.patch(
        f"/api/v1/transfers/{transfer_id}",
        json={
            "status": "approved",
            "approved_by": str(approver.id),
            "effective_date": "2026-10-01",
        },
        headers=auth_cmd,
    )
    assert len(await _outbox_rows("TransferStatusChanged")) == 1

    r = await client.patch(
        f"/api/v1/transfers/{transfer_id}", json={"status": "rejected"}, headers=auth_cmd
    )
    assert r.status_code == 409
    assert len(await _outbox_rows("TransferStatusChanged")) == 1  # unchanged


async def test_promotion_and_performance_review_enqueue(client, auth_hr, make_officer):
    officer = await make_officer()
    approver = await make_officer()
    reviewer = await make_officer()
    r1 = await client.post(
        f"/api/v1/officers/{officer.id}/promotions",
        json={
            "new_rank": "Sergeant",
            "effective_date": "2026-10-01",
            "approved_by": str(approver.id),
        },
        headers=auth_hr,
    )
    r2 = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "80"},
        headers=auth_hr,
    )

    promo_rows = await _outbox_rows("PromotionRecorded")
    review_rows = await _outbox_rows("PerformanceReviewRecorded")
    assert len(promo_rows) == 1 and promo_rows[0].aggregate_id == r1.json()["id"]
    assert len(review_rows) == 1 and review_rows[0].aggregate_id == r2.json()["id"]


async def test_event_id_is_unique(client, auth_hr, make_unit):
    for i in range(3):
        await client.post(
            "/api/v1/units",
            json={"name": f"Unit-{i}", "station_id": str(uuid.uuid4())},
            headers=auth_hr,
        )
    rows = await _outbox_rows("UnitCreated")
    ids = [str(r.event_id) for r in rows]
    assert len(ids) == len(set(ids)) == 3


async def test_relay_publishes_officer_created_to_kafka_and_marks_sent(
    client, auth_hr, make_unit, outbox_relay, read_kafka
):
    unit = await make_unit()
    r = await client.post(
        "/api/v1/officers",
        json={
            "user_id": str(uuid.uuid4()),
            "badge_number": "OUTBOX-KAFKA",
            "rank": "Constable",
            "unit_id": str(unit.id),
            "hire_date": "2020-01-01",
        },
        headers=auth_hr,
    )
    officer_id = r.json()["id"]

    published = await outbox_relay.drain_once()
    assert published == 1

    rows = await _outbox_rows("OfficerCreated")
    assert rows[0].published_at is not None

    events = await read_kafka("OfficerCreated", expected=1)
    assert len(events) == 1
    assert events[0]["event_type"] == "OfficerCreated"
    assert events[0]["aggregate_id"] == officer_id

    assert await outbox_relay.drain_once() == 0  # already published, no-op
