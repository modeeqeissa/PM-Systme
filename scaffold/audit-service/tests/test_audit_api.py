"""GET /audit + GET /audit/verify — read-only oversight access (FR-AUD-03)."""
import uuid


async def _seed(emit, consumer, n_case=2, n_evidence=1, actor=None):
    actor = actor or str(uuid.uuid4())
    for _ in range(n_case):
        await emit("CaseOpened", {"case_id": str(uuid.uuid4())},
                   actor_id=actor, actor_role="Auditor", service="case-service")
    for _ in range(n_evidence):
        await emit("EvidenceLogged", {"evidence_id": str(uuid.uuid4())},
                   service="evidence-service")
    await consumer.process_available(timeout=5.0)
    return actor


async def test_query_returns_entries_newest_first(client, emit, consumer, auth_read):
    await _seed(emit, consumer, n_case=3, n_evidence=0)
    r = await client.get("/api/v1/audit", headers=auth_read)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert [e["id"] for e in body] == sorted((e["id"] for e in body), reverse=True)
    assert set(body[0]) >= {
        "id", "actor_id", "actor_role", "service_name", "entity_type",
        "entity_id", "action", "timestamp", "prev_hash", "record_hash", "metadata",
    }


async def test_filters(client, emit, consumer, auth_read):
    actor = await _seed(emit, consumer, n_case=2, n_evidence=2)
    only_case = await client.get(
        "/api/v1/audit?entity_type=case", headers=auth_read
    )
    assert {e["entity_type"] for e in only_case.json()} == {"case"}

    by_actor = await client.get(f"/api/v1/audit?actor_id={actor}", headers=auth_read)
    assert all(e["actor_id"] == actor for e in by_actor.json())
    assert len(by_actor.json()) == 2  # only the CaseOpened ones used this actor

    by_service = await client.get(
        "/api/v1/audit?service_name=evidence-service", headers=auth_read
    )
    assert {e["service_name"] for e in by_service.json()} == {"evidence-service"}

    creates = await client.get("/api/v1/audit?action=create", headers=auth_read)
    assert {e["action"] for e in creates.json()} == {"create"}


async def test_verify_endpoint_reports_valid_chain(client, emit, consumer, auth_read):
    await _seed(emit, consumer, n_case=3, n_evidence=1)
    r = await client.get("/api/v1/audit/verify", headers=auth_read)
    assert r.status_code == 200
    assert r.json() == {"entries_checked": 4, "valid": True, "broken_at": None}


async def test_requires_audit_read_permission(client, auth_none):
    assert (await client.get("/api/v1/audit", headers=auth_none)).status_code == 403
    assert (await client.get("/api/v1/audit/verify", headers=auth_none)).status_code == 403


async def test_requires_a_token(client):
    assert (await client.get("/api/v1/audit")).status_code == 401


async def test_no_write_endpoints_exist(client, auth_read):
    # audit-service accepts writes only from Kafka; there is no create/update/delete API
    for method in ("post", "put", "patch", "delete"):
        r = await client.request(method, "/api/v1/audit", headers=auth_read)
        assert r.status_code == 405
