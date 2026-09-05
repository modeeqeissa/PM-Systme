import uuid


async def test_adapter_call_returns_mock_response_and_correlation_header(client, auth_ict):
    r = await client.post(
        "/api/v1/adapters/CAD/call", json={"unit_id": "u-1", "status": "available"}, headers=auth_ict
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mock"] is True
    assert body["system_name"] == "CAD"
    assert body["request_echo"] == {"unit_id": "u-1", "status": "available"}
    assert "X-Correlation-Id" in r.headers
    assert body["correlation_id"] == r.headers["X-Correlation-Id"]


async def test_adapter_call_is_case_insensitive(client, auth_ict):
    r = await client.post("/api/v1/adapters/jail/call", json={}, headers=auth_ict)
    assert r.status_code == 200
    assert r.json()["system_name"] == "JAIL"


async def test_adapter_call_honours_supplied_correlation_id(client, auth_ict):
    corr = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/adapters/NCDB/call",
        json={"q": "check"},
        headers={**auth_ict, "X-Correlation-Id": corr},
    )
    assert r.status_code == 200
    assert r.json()["correlation_id"] == corr
    assert r.headers["X-Correlation-Id"] == corr


async def test_adapter_call_logs_inbound_and_outbound_pair(client, auth_ict):
    corr = str(uuid.uuid4())
    await client.post(
        "/api/v1/adapters/COURTS/call",
        json={"case": "c-9"},
        headers={**auth_ict, "X-Correlation-Id": corr},
    )
    r = await client.get(
        "/api/v1/external-system-logs",
        params={"correlation_id": corr},
        headers=auth_ict,
    )
    assert r.status_code == 200
    rows = r.json()
    assert {row["direction"] for row in rows} == {"inbound", "outbound"}
    assert all(row["system_name"] == "COURTS" for row in rows)
    outbound = next(row for row in rows if row["direction"] == "outbound")
    assert outbound["response_status"] == 200


async def test_adapter_call_unknown_system_404(client, auth_ict):
    r = await client.post("/api/v1/adapters/INTERPOL/call", json={}, headers=auth_ict)
    assert r.status_code == 404


async def test_adapter_call_disabled_system_409_and_logs_nothing(client, auth_ict):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    cad = next(c for c in r.json() if c["system_name"] == "CAD")
    await client.patch(
        f"/api/v1/integration-configs/{cad['id']}",
        json={"enabled": False},
        headers=auth_ict,
    )

    r = await client.post("/api/v1/adapters/CAD/call", json={}, headers=auth_ict)
    assert r.status_code == 409

    r = await client.get(
        "/api/v1/external-system-logs", params={"system_name": "CAD"}, headers=auth_ict
    )
    assert r.json() == []


async def test_adapter_call_requires_integration_write(client, auth_none):
    r = await client.post("/api/v1/adapters/CAD/call", json={}, headers=auth_none)
    assert r.status_code == 403


async def test_external_system_logs_require_integration_read(client, auth_none):
    r = await client.get("/api/v1/external-system-logs", headers=auth_none)
    assert r.status_code == 403


async def test_adapters_require_auth(client):
    r = await client.post("/api/v1/adapters/CAD/call", json={})
    assert r.status_code == 401
