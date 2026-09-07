"""Optional Idempotency-Key on POST /evidence (CLAUDE.md rule 6 / TD-006).

Mirrors case-service's incident idempotency tests, for the multipart upload:
a replay with the same key returns the original item and does NOT re-hash,
re-store, or re-emit.
"""
import hashlib
import uuid

from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import OwnerSession

PATH = "/api/v1/evidence"


def _form(**over) -> dict:
    d = {
        "case_id": str(uuid.uuid4()),
        "item_type": "physical",
        "description": "One kitchen knife, bagged and tagged.",
        "collected_by": str(uuid.uuid4()),
        "collected_at": "2026-09-03T10:15:00+00:00",
    }
    d.update(over)
    return d


async def _logged_events() -> list[OutboxEvent]:
    async with OwnerSession() as s:
        return list(
            (await s.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "EvidenceLogged"))).all()
        )


async def test_replay_same_key_returns_200_with_original_and_no_re_hash(client, auth_full):
    key = str(uuid.uuid4())
    content = b"seized-disk-image-bytes"
    sha = hashlib.sha256(content).hexdigest()

    first = await client.post(
        PATH,
        data=_form(item_type="digital_file", description="disk image"),
        files={"file": ("image.bin", content, "application/octet-stream")},
        headers={**auth_full, "Idempotency-Key": key},
    )
    assert first.status_code == 201, first.text
    original = first.json()
    assert original["sha256_hash"] == sha

    # replay: different metadata + a different file — all ignored
    replay = await client.post(
        PATH,
        data=_form(item_type="weapon", description="totally different"),
        files={"file": ("other.bin", b"different-bytes", "application/octet-stream")},
        headers={**auth_full, "Idempotency-Key": key},
    )
    assert replay.status_code == 200
    assert replay.json() == original  # same id, same hash, same everything
    assert replay.json()["sha256_hash"] == sha

    assert len(await _logged_events()) == 1  # EvidenceLogged fired once


async def test_distinct_keys_create_distinct_items(client, auth_full):
    r1 = await client.post(PATH, data=_form(), headers={**auth_full, "Idempotency-Key": str(uuid.uuid4())})
    r2 = await client.post(PATH, data=_form(), headers={**auth_full, "Idempotency-Key": str(uuid.uuid4())})
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    assert len(await _logged_events()) == 2


async def test_no_key_always_creates(client, auth_full):
    r1 = await client.post(PATH, data=_form(), headers=auth_full)
    r2 = await client.post(PATH, data=_form(), headers=auth_full)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    assert "client_sync_id" not in r1.json()


async def test_replay_also_skips_a_second_custody_event(client, auth_full):
    key = str(uuid.uuid4())
    first = await client.post(PATH, data=_form(), headers={**auth_full, "Idempotency-Key": key})
    item_id = first.json()["id"]
    await client.post(PATH, data=_form(), headers={**auth_full, "Idempotency-Key": key})

    chain = await client.get(f"{PATH}/{item_id}/custody", headers=auth_full)
    assert chain.status_code == 200
    assert len(chain.json()) == 1  # only the original 'collected' event
