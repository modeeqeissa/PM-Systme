"""POST/GET /evidence/{id}/custody — append-only chain + acknowledgement (FR-EVID-03/04)."""
import uuid


def _url(evidence_id) -> str:
    return f"/api/v1/evidence/{evidence_id}/custody"


async def test_record_stored_event_appends_to_chain(client, make_item, auth_full):
    item = await make_item()
    r = await client.post(
        _url(item.id),
        json={"action": "stored", "from_officer": str(uuid.uuid4())},
        headers=auth_full,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["action"] == "stored"
    assert body["acknowledgement"] is False
    assert isinstance(body["id"], int)

    chain = (await client.get(_url(item.id), headers=auth_full)).json()
    assert [e["action"] for e in chain] == ["collected", "stored"]
    assert chain[0]["id"] < chain[1]["id"]  # sequential, ordered


async def test_transfer_requires_receiving_ack(client, make_item, auth_full):
    item = await make_item()
    # no to_officer / signature -> 400
    r = await client.post(
        _url(item.id), json={"action": "transferred"}, headers=auth_full
    )
    assert r.status_code == 400

    # with both -> 201, and the raw PIN is not echoed back
    r = await client.post(
        _url(item.id),
        json={
            "action": "transferred",
            "from_officer": str(uuid.uuid4()),
            "to_officer": str(uuid.uuid4()),
            "acknowledgement_signature": "1234-pin",
        },
        headers=auth_full,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["acknowledgement"] is True
    assert "acknowledgement_signature" not in body
    assert "1234-pin" not in r.text


async def test_signature_is_stored_only_as_a_hash(client, make_item, auth_full, request):
    item = await make_item()
    await client.post(
        _url(item.id),
        json={
            "action": "submitted_court",
            "to_officer": str(uuid.uuid4()),
            "acknowledgement_signature": "secret-pin-9999",
        },
        headers=auth_full,
    )
    from sqlalchemy import select

    from app.models import CustodyEvent
    from tests.conftest import OwnerSession

    async with OwnerSession() as s:
        rows = (
            await s.scalars(
                select(CustodyEvent).where(CustodyEvent.action == "submitted_court")
            )
        ).all()
    assert len(rows) == 1
    stored = rows[0].acknowledgement_signature
    assert stored is not None and stored != "secret-pin-9999"
    assert len(stored) == 64  # sha-256 hex


async def test_custody_action_updates_item_status(client, make_item, auth_full):
    item = await make_item()
    await client.post(_url(item.id), json={"action": "analyzed"}, headers=auth_full)
    r = await client.get(f"/api/v1/evidence/{item.id}", headers=auth_full)
    assert r.json()["status"] == "in_analysis"

    await client.post(
        _url(item.id),
        json={
            "action": "submitted_court",
            "to_officer": str(uuid.uuid4()),
            "acknowledgement_signature": "pin",
        },
        headers=auth_full,
    )
    r = await client.get(f"/api/v1/evidence/{item.id}", headers=auth_full)
    assert r.json()["status"] == "in_court"


async def test_custody_rejects_unknown_action(client, make_item, auth_full):
    item = await make_item()
    r = await client.post(
        _url(item.id), json={"action": "teleported"}, headers=auth_full
    )
    assert r.status_code == 422


async def test_custody_404_for_unknown_item(client, auth_full):
    r = await client.post(_url(uuid.uuid4()), json={"action": "stored"}, headers=auth_full)
    assert r.status_code == 404
    r = await client.get(_url(uuid.uuid4()), headers=auth_full)
    assert r.status_code == 404


async def test_record_requires_custody_write(client, make_item, auth_read):
    item = await make_item()
    r = await client.post(_url(item.id), json={"action": "stored"}, headers=auth_read)
    assert r.status_code == 403


async def test_list_requires_vault_read(client, make_item, auth_none):
    item = await make_item()
    r = await client.get(_url(item.id), headers=auth_none)
    assert r.status_code == 403
