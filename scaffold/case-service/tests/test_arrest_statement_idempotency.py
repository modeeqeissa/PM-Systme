"""Optional Idempotency-Key on POST /cases/{id}/arrests and .../statements
(CLAUDE.md rule 6 / TD-006). Mirrors test_incidents.py."""
import uuid

import pytest
from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal


async def _outbox(event_type: str) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        return list(
            (await s.scalars(select(OutboxEvent).where(OutboxEvent.event_type == event_type))).all()
        )


def _arrest_body(**over):
    b = {
        "officer_id": str(uuid.uuid4()),
        "suspect_id": str(uuid.uuid4()),
        "arrest_date": "2026-09-03T12:00:00+00:00",
        "legal_basis": "caught in the act",
    }
    b.update(over)
    return b


def _statement_body(**over):
    b = {
        "recorded_by": str(uuid.uuid4()),
        "party_type": "witness",
        "statement_text": "I saw the whole thing.",
    }
    b.update(over)
    return b


RESOURCES = [
    ("arrests", _arrest_body, "ArrestRecorded", "legal_basis", "caught in the act"),
    ("statements", _statement_body, "StatementRecorded", "statement_text", "I saw the whole thing."),
]


async def _valid_extra(path: str, make_person) -> dict:
    """arrests.suspect_id is a real FK now — the body needs a person that exists."""
    if path == "arrests":
        return {"suspect_id": str((await make_person()).id)}
    return {}


@pytest.mark.parametrize("path,body_fn,event,field,val", RESOURCES)
async def test_replay_same_key_returns_200_with_original(
    client, make_case, make_person, auth_rw, path, body_fn, event, field, val
):
    case = await make_case(status="investigating")
    extra = await _valid_extra(path, make_person)
    key = str(uuid.uuid4())
    url = f"/api/v1/cases/{case.id}/{path}"

    first = await client.post(
        url, json=body_fn(**{field: val}, **extra), headers={**auth_rw, "Idempotency-Key": key}
    )
    assert first.status_code == 201, first.text
    original = first.json()

    # a different body under the same key is ignored — original comes back
    changed = {field: "totally different"} if field != "party_type" else {}
    replay = await client.post(
        url, json=body_fn(**changed, **extra), headers={**auth_rw, "Idempotency-Key": key}
    )
    assert replay.status_code == 200
    assert replay.json() == original
    assert replay.json()[field] == val

    # the domain event fired once, not on the replay
    assert len(await _outbox(event)) == 1


@pytest.mark.parametrize("path,body_fn,event,field,val", RESOURCES)
async def test_distinct_keys_create_distinct_records(
    client, make_case, make_person, auth_rw, path, body_fn, event, field, val
):
    case = await make_case(status="investigating")
    extra = await _valid_extra(path, make_person)
    url = f"/api/v1/cases/{case.id}/{path}"
    r1 = await client.post(url, json=body_fn(**extra), headers={**auth_rw, "Idempotency-Key": str(uuid.uuid4())})
    r2 = await client.post(url, json=body_fn(**extra), headers={**auth_rw, "Idempotency-Key": str(uuid.uuid4())})
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    assert len(await _outbox(event)) == 2


@pytest.mark.parametrize("path,body_fn,event,field,val", RESOURCES)
async def test_no_key_always_creates(
    client, make_case, make_person, auth_rw, path, body_fn, event, field, val
):
    case = await make_case(status="investigating")
    extra = await _valid_extra(path, make_person)
    url = f"/api/v1/cases/{case.id}/{path}"
    r1 = await client.post(url, json=body_fn(**extra), headers=auth_rw)
    r2 = await client.post(url, json=body_fn(**extra), headers=auth_rw)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    assert "client_sync_id" not in r1.json()


@pytest.mark.parametrize("path,body_fn,event,field,val", RESOURCES)
async def test_replay_survives_a_service_restart_shape(
    client, make_case, make_person, auth_rw, path, body_fn, event, field, val
):
    """A second request minutes later (new connection) with the same key still
    dedupes — the key lives in the row, not in memory."""
    case = await make_case(status="investigating")
    extra = await _valid_extra(path, make_person)
    url = f"/api/v1/cases/{case.id}/{path}"
    key = str(uuid.uuid4())
    first = await client.post(url, json=body_fn(**extra), headers={**auth_rw, "Idempotency-Key": key})
    assert first.status_code == 201
    async with SessionLocal() as _s:  # force a fresh session/connection
        pass
    replay = await client.post(url, json=body_fn(**extra), headers={**auth_rw, "Idempotency-Key": key})
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
