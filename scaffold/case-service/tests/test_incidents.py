"""POST /api/v1/incidents — creation + Idempotency-Key handling (FR-CASE-01/10).

Tokens come from iam-service's real login/MFA flow (see conftest): E2E-RW holds
case.write, E2E-RO does not.
"""
import uuid

PATH = "/api/v1/incidents"


def _payload(**over):
    body = {
        "reported_by": str(uuid.uuid4()),
        "incident_type": "burglary",
        "description": "Forced entry reported at the rear door.",
        "latitude": -1.286389,
        "longitude": 36.817223,
        "station_id": str(uuid.uuid4()),
        "reported_at": "2026-09-03T08:30:00+00:00",
    }
    body.update(over)
    return body


def _hdr(auth: dict, key: str | None = None) -> dict:
    h = dict(auth)
    if key is not None:
        h["Idempotency-Key"] = key
    return h


async def test_create_incident_returns_201_and_contract_shape(client, auth_rw):
    body = _payload()
    r = await client.post(PATH, json=body, headers=_hdr(auth_rw, str(uuid.uuid4())))
    assert r.status_code == 201
    data = r.json()
    assert set(data) == {
        "id", "reported_by", "incident_type", "description",
        "latitude", "longitude", "station_id", "reported_at", "created_at",
    }
    assert data["incident_type"] == "burglary"
    assert data["reported_by"] == body["reported_by"]
    uuid.UUID(data["id"])
    assert "client_sync_id" not in data


async def test_missing_idempotency_key_is_rejected(client, auth_rw):
    r = await client.post(PATH, json=_payload(), headers=auth_rw)
    assert r.status_code == 422


async def test_optional_geo_fields_may_be_omitted(client, auth_rw):
    body = _payload()
    body.pop("latitude")
    body.pop("longitude")
    r = await client.post(PATH, json=body, headers=_hdr(auth_rw, str(uuid.uuid4())))
    assert r.status_code == 201
    assert r.json()["latitude"] is None
    assert r.json()["longitude"] is None


async def test_idempotent_replay_returns_200_with_original_record(client, auth_rw):
    key = str(uuid.uuid4())
    first = await client.post(
        PATH, json=_payload(incident_type="theft"), headers=_hdr(auth_rw, key)
    )
    assert first.status_code == 201
    original = first.json()

    replay = await client.post(
        PATH,
        json=_payload(incident_type="assault", description="different"),
        headers=_hdr(auth_rw, key),
    )
    assert replay.status_code == 200
    assert replay.json() == original
    assert replay.json()["incident_type"] == "theft"


async def test_distinct_keys_create_distinct_incidents(client, auth_rw):
    r1 = await client.post(PATH, json=_payload(), headers=_hdr(auth_rw, str(uuid.uuid4())))
    r2 = await client.post(PATH, json=_payload(), headers=_hdr(auth_rw, str(uuid.uuid4())))
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


async def test_write_permission_required(client, auth_ro):
    # E2E-RO (Station Commander) has case.read but not case.write.
    r = await client.post(
        PATH, json=_payload(), headers=_hdr(auth_ro, str(uuid.uuid4()))
    )
    assert r.status_code == 403


async def test_unauthenticated_request_is_rejected(client):
    r = await client.post(
        PATH, json=_payload(), headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    assert r.status_code == 401
