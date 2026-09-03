"""Hash-chain construction + tamper detection (FR-AUD-02)."""
import datetime as dt
import uuid

from app.services.hashchain import GENESIS, compute_record_hash, verify_chain
from tests.conftest import OwnerSession, owner_conn


def _entry(**over) -> dict:
    e = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "Investigator",
        "service_name": "case-service",
        "entity_type": "case",
        "entity_id": str(uuid.uuid4()),
        "action": "create",
        "timestamp": dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc),
        "metadata": {"k": "v"},
    }
    e.update(over)
    return e


def test_record_hash_is_deterministic_and_prev_sensitive():
    e = _entry()
    assert compute_record_hash(GENESIS, e) == compute_record_hash(GENESIS, e)
    assert compute_record_hash(GENESIS, e) != compute_record_hash("f" * 64, e)
    assert compute_record_hash(GENESIS, e) != compute_record_hash(
        GENESIS, _entry(entity_id="other", **{k: e[k] for k in e if k != "entity_id"})
    )


async def test_append_entry_builds_a_valid_chain(client, emit, consumer):
    for _ in range(3):
        await emit("CaseOpened", {"case_id": str(uuid.uuid4())})
    await consumer.process_available(timeout=5.0)

    async with OwnerSession() as s:
        checked, valid, broken_at = await verify_chain(s)
    assert checked == 3 and valid is True and broken_at is None


async def test_verify_detects_a_tampered_entry(client, emit, consumer):
    for _ in range(4):
        await emit("CaseOpened", {"case_id": str(uuid.uuid4())})
    await consumer.process_available(timeout=5.0)

    # Tamper: rewrite entry #2's metadata AS THE OWNER, bypassing the append-only
    # trigger via session_replication_role. (The app role could never do this -
    # see test_append_only.py.)
    conn = owner_conn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM audit_logs ORDER BY id OFFSET 1 LIMIT 1")
        tampered_id = cur.fetchone()[0]
        cur.execute("SET session_replication_role = replica")
        cur.execute(
            "UPDATE audit_logs SET metadata = %s::jsonb WHERE id = %s",
            ('{"tampered": true}', tampered_id),
        )
        cur.execute("SET session_replication_role = default")
    finally:
        conn.close()

    async with OwnerSession() as s:
        checked, valid, broken_at = await verify_chain(s)
    assert checked == 4 and valid is False
    assert broken_at == tampered_id
