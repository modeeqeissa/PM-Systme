"""GET /dashboard/kpis — aggregated snapshot from the read models (FR-DASH-01)."""
import uuid


async def _seed_station(emit, station: str, *, opened: int, incident_type="assault"):
    for _ in range(opened):
        await emit(
            "CaseOpened",
            {"case_id": str(uuid.uuid4()), "station_id": station,
             "incident_type": incident_type, "opened_at": "2026-09-03T00:00:00+00:00"},
        )


async def test_force_wide_snapshot(client, emit, consumer, auth_view):
    s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
    await _seed_station(emit, s1, opened=2, incident_type="burglary")
    await _seed_station(emit, s2, opened=1, incident_type="theft")
    await consumer.process_available(timeout=6.0)

    r = await client.get("/api/v1/dashboard/kpis", headers=auth_view)
    assert r.status_code == 200
    body = r.json()
    assert body["station_id"] is None
    assert body["cases"]["opened"] == 3
    assert body["cases"]["closed"] == 0
    assert body["cases"]["avg_case_age_days"] is None
    types = {b["incident_type"] for b in body["crime_trends"]}
    assert types == {"burglary", "theft"}
    assert set(body["evidence_integrity"]) == {
        "evidence_logged", "pending_transfer_ack", "hash_mismatches"
    }


async def test_station_filter(client, emit, consumer, auth_view):
    s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
    await _seed_station(emit, s1, opened=3)
    await _seed_station(emit, s2, opened=5)
    await consumer.process_available(timeout=6.0)

    r = await client.get(f"/api/v1/dashboard/kpis?station_id={s1}", headers=auth_view)
    assert r.json()["cases"]["opened"] == 3
    assert r.json()["station_id"] == s1


async def test_avg_case_age_after_close(client, emit, consumer, auth_view):
    station = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    await emit("CaseOpened", {"case_id": case_id, "station_id": station,
                              "opened_at": "2026-09-01T00:00:00+00:00"})
    await emit("CaseStatusChanged", {"case_id": case_id, "from_status": "open",
                                     "to_status": "closed",
                                     "closed_at": "2026-09-11T00:00:00+00:00"})
    await consumer.process_available(timeout=6.0)

    body = (await client.get("/api/v1/dashboard/kpis", headers=auth_view)).json()
    assert body["cases"]["closed"] == 1
    assert body["cases"]["avg_case_age_days"] == 10.0


async def test_date_range_excludes_out_of_window_months(client, emit, consumer, auth_view):
    station = str(uuid.uuid4())
    await emit("CaseOpened", {"case_id": str(uuid.uuid4()), "station_id": station,
                              "incident_type": "x", "opened_at": "2026-01-15T00:00:00+00:00"})
    await emit("CaseOpened", {"case_id": str(uuid.uuid4()), "station_id": station,
                              "incident_type": "x", "opened_at": "2026-09-15T00:00:00+00:00"})
    await consumer.process_available(timeout=6.0)

    r = await client.get(
        "/api/v1/dashboard/kpis?from=2026-06-01&to=2026-12-31", headers=auth_view
    )
    body = r.json()
    assert body["cases"]["opened"] == 1
    assert {b["month"] for b in body["crime_trends"]} == {"2026-09-01"}


async def test_requires_dashboard_view(client, auth_none):
    assert (await client.get("/api/v1/dashboard/kpis", headers=auth_none)).status_code == 403


async def test_requires_a_token(client):
    assert (await client.get("/api/v1/dashboard/kpis")).status_code == 401


async def test_no_write_endpoints(client, auth_view):
    for method in ("post", "put", "patch", "delete"):
        r = await client.request(method, "/api/v1/dashboard/kpis", headers=auth_view)
        assert r.status_code == 405
