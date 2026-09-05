"""FR-DASH-02 mv_unit_readiness — certified_officer_pct + on_leave_count per unit,
computed at read time from the hr/training event dimensions."""
import datetime as dt
import uuid


async def test_unit_readiness_from_hr_and_training_events(client, emit, consumer, auth_view):
    station = str(uuid.uuid4())
    unit = str(uuid.uuid4())
    o1, o2, o3 = (str(uuid.uuid4()) for _ in range(3))

    await emit("UnitCreated", {"unit_id": unit, "name": "Traffic", "station_id": station})
    for o in (o1, o2, o3):
        await emit("OfficerCreated", {"officer_id": o, "user_id": str(uuid.uuid4()),
                                      "unit_id": unit, "status": "active"})
    # o1 + o2 certified, o3 not
    await emit("OfficerCertificationIssued", {
        "officer_certification_id": str(uuid.uuid4()), "officer_id": o1,
        "issued_date": "2026-01-01", "expires_date": "2027-01-01", "status": "active"})
    await emit("OfficerCertificationIssued", {
        "officer_certification_id": str(uuid.uuid4()), "officer_id": o2,
        "issued_date": "2026-01-01", "expires_date": "2026-10-01", "status": "expiring_soon"})

    # o3 currently on approved leave
    lr = str(uuid.uuid4())
    today = dt.date.today()
    await emit("LeaveRequested", {
        "leave_request_id": lr, "officer_id": o3, "leave_type": "annual",
        "start_date": (today - dt.timedelta(days=1)).isoformat(),
        "end_date": (today + dt.timedelta(days=5)).isoformat()})
    await emit("LeaveStatusChanged", {
        "leave_request_id": lr, "officer_id": o3, "from_status": "pending",
        "to_status": "approved", "approved_by": str(uuid.uuid4())})

    await consumer.process_available(timeout=8.0)

    body = (await client.get("/api/v1/dashboard/kpis", headers=auth_view)).json()
    rows = body["unit_readiness"]
    assert len(rows) == 1
    row = rows[0]
    assert row["unit_id"] == unit
    assert row["station_id"] == station
    assert row["unit_name"] == "Traffic"
    assert row["total_officers"] == 3
    assert row["certified_officer_pct"] == 200.0 / 3
    assert row["on_leave_count"] == 1


async def test_expired_cert_does_not_count_as_certified(client, emit, consumer, auth_view):
    station, unit, officer = (str(uuid.uuid4()) for _ in range(3))
    await emit("UnitCreated", {"unit_id": unit, "name": "K9", "station_id": station})
    await emit("OfficerCreated", {"officer_id": officer, "user_id": str(uuid.uuid4()),
                                  "unit_id": unit, "status": "active"})
    oc = str(uuid.uuid4())
    await emit("OfficerCertificationIssued", {
        "officer_certification_id": oc, "officer_id": officer,
        "issued_date": "2020-01-01", "expires_date": "2021-01-01", "status": "active"})
    await emit("OfficerCertificationStatusChanged", {
        "officer_certification_id": oc, "officer_id": officer,
        "from_status": "active", "to_status": "expired"})
    await consumer.process_available(timeout=6.0)

    row = (await client.get("/api/v1/dashboard/kpis", headers=auth_view)).json()["unit_readiness"][0]
    assert row["total_officers"] == 1
    assert row["certified_officer_pct"] == 0.0


async def test_approved_transfer_moves_officer_between_units(client, emit, consumer, auth_view):
    station = str(uuid.uuid4())
    unit_a, unit_b = str(uuid.uuid4()), str(uuid.uuid4())
    officer = str(uuid.uuid4())
    transfer = str(uuid.uuid4())

    await emit("UnitCreated", {"unit_id": unit_a, "name": "A", "station_id": station})
    await emit("UnitCreated", {"unit_id": unit_b, "name": "B", "station_id": station})
    await emit("OfficerCreated", {"officer_id": officer, "user_id": str(uuid.uuid4()),
                                  "unit_id": unit_a, "status": "active"})
    await emit("TransferRequested", {"transfer_id": transfer, "officer_id": officer,
                                     "from_unit_id": unit_a, "to_unit_id": unit_b})
    await emit("TransferStatusChanged", {"transfer_id": transfer, "officer_id": officer,
                                         "from_status": "pending", "to_status": "approved",
                                         "effective_date": "2026-10-01",
                                         "approved_by": str(uuid.uuid4())})
    await consumer.process_available(timeout=6.0)

    rows = {r["unit_name"]: r for r in
            (await client.get("/api/v1/dashboard/kpis", headers=auth_view)).json()["unit_readiness"]}
    assert rows["A"]["total_officers"] == 0
    assert rows["B"]["total_officers"] == 1


async def test_unit_readiness_station_filtered(client, emit, consumer, auth_view):
    s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    await emit("UnitCreated", {"unit_id": u1, "name": "U1", "station_id": s1})
    await emit("UnitCreated", {"unit_id": u2, "name": "U2", "station_id": s2})
    await consumer.process_available(timeout=6.0)

    body = (await client.get(f"/api/v1/dashboard/kpis?station_id={s1}", headers=auth_view)).json()
    assert [r["unit_id"] for r in body["unit_readiness"]] == [u1]
