"""Events -> CQRS read models (docs Section 9.3.7); idempotent (SRS §9.4)."""
import datetime as dt
import uuid

from sqlalchemy import select

from app.models import (
    DashCase,
    MvCrimeTrends,
    MvEvidenceIntegrity,
    MvStationCaseKpis,
)
from tests.conftest import SessionLocal, _BASE_TOPIC


async def _one(model):
    async with SessionLocal() as s:
        return list((await s.scalars(select(model))).all())


async def test_case_opened_updates_case_kpis_and_crime_trends(client, emit, consumer):
    station = str(uuid.uuid4())
    await emit(
        "CaseOpened",
        {
            "case_id": str(uuid.uuid4()),
            "station_id": station,
            "incident_type": "burglary",
            "opened_at": "2026-09-03T09:00:00+00:00",
        },
    )
    assert await consumer.process_available() == 1

    kpis = await _one(MvStationCaseKpis)
    assert len(kpis) == 1
    assert str(kpis[0].station_id) == station
    assert kpis[0].day == dt.date(2026, 9, 3)
    assert kpis[0].open_cases == 1 and kpis[0].closed_cases == 0

    trends = await _one(MvCrimeTrends)
    assert len(trends) == 1
    assert trends[0].incident_type == "burglary"
    assert trends[0].month == dt.date(2026, 9, 1)
    assert trends[0].count == 1

    assert len(await _one(DashCase)) == 1


async def test_case_close_records_closed_count_and_age(client, emit, consumer):
    station = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    await emit(
        "CaseOpened",
        {"case_id": case_id, "station_id": station, "incident_type": "theft",
         "opened_at": "2026-09-01T00:00:00+00:00"},
    )
    await emit(
        "CaseStatusChanged",
        {"case_id": case_id, "from_status": "investigating", "to_status": "closed",
         "closed_at": "2026-09-06T00:00:00+00:00"},
    )
    assert await consumer.process_available() == 2

    async with SessionLocal() as s:
        rows = (await s.scalars(select(MvStationCaseKpis).order_by(MvStationCaseKpis.day))).all()
    # one bucket for the open day, one for the close day
    close_row = next(r for r in rows if r.day == dt.date(2026, 9, 6))
    assert close_row.closed_cases == 1
    assert float(close_row.sum_age_days) == 5.0

    dc = (await _one(DashCase))[0]
    assert dc.closed is True


async def test_non_close_status_change_is_ignored(client, emit, consumer):
    case_id = str(uuid.uuid4())
    await emit("CaseOpened", {"case_id": case_id, "station_id": str(uuid.uuid4()),
                              "opened_at": "2026-09-01T00:00:00+00:00"})
    await emit("CaseStatusChanged", {"case_id": case_id, "from_status": "open",
                                     "to_status": "investigating", "closed_at": None})
    assert await consumer.process_available() == 2
    async with SessionLocal() as s:
        total_closed = sum(
            r.closed_cases for r in (await s.scalars(select(MvStationCaseKpis))).all()
        )
    assert total_closed == 0


async def test_arrest_recorded_increments_when_case_known(client, emit, consumer):
    station = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    await emit("CaseOpened", {"case_id": case_id, "station_id": station,
                              "opened_at": "2026-09-03T00:00:00+00:00"})
    await emit("ArrestRecorded", {"arrest_id": str(uuid.uuid4()), "case_id": case_id},
               occurred_at="2026-09-04T00:00:00+00:00")
    assert await consumer.process_available() == 2
    async with SessionLocal() as s:
        rows = (await s.scalars(select(MvStationCaseKpis))).all()
    assert sum(r.arrests_recorded for r in rows) == 1


async def test_evidence_logged_transfer_and_hash_mismatch(client, emit, consumer):
    ev_id = str(uuid.uuid4())
    await emit("EvidenceLogged", {"evidence_id": ev_id, "case_id": str(uuid.uuid4())},
               service="evidence-service")
    await emit(
        "CustodyEventRecorded",
        {"custody_event_id": 1, "evidence_id": ev_id, "action": "transferred",
         "acknowledgement": False},
        service="evidence-service",
    )
    await emit(
        "EvidenceHashMismatch",
        {"evidence_id": ev_id, "stored_hash": "a" * 64, "computed_hash": "b" * 64},
        service="evidence-service",
    )
    assert await consumer.process_available() == 3
    rows = await _one(MvEvidenceIntegrity)
    assert len(rows) == 1
    assert rows[0].evidence_logged == 1
    assert rows[0].pending_transfer_ack_count == 1
    assert rows[0].hash_mismatch_count == 1


async def test_redelivery_does_not_double_count(client, emit, consumer):
    env = await emit("CaseOpened", {"case_id": str(uuid.uuid4()), "station_id": str(uuid.uuid4()),
                                    "opened_at": "2026-09-03T00:00:00+00:00"})
    assert await consumer.process_available() == 1

    import json
    import os

    from aiokafka import AIOKafkaProducer

    prod = AIOKafkaProducer(bootstrap_servers=os.environ["EVENTS_KAFKA_BOOTSTRAP"])
    await prod.start()
    try:
        await prod.send_and_wait(
            os.environ["EVENTS_TOPIC_PREFIX"] + _BASE_TOPIC["CaseOpened"],
            json.dumps(env).encode(),
        )
    finally:
        await prod.stop()

    assert await consumer.process_available() == 0
    async with SessionLocal() as s:
        rows = (await s.scalars(select(MvStationCaseKpis))).all()
    assert sum(r.open_cases for r in rows) == 1
