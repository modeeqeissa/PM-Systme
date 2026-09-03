"""POST /evidence, GET /evidence/{id}, POST /evidence/{id}/verify (FR-EVID-01/02/06)."""
import hashlib
import uuid

PATH = "/api/v1/evidence"


def _form(**over) -> dict:
    data = {
        "case_id": str(uuid.uuid4()),
        "item_type": "physical",
        "description": "One kitchen knife, bagged and tagged.",
        "collected_by": str(uuid.uuid4()),
        "collected_at": "2026-09-03T10:15:00+00:00",
    }
    data.update(over)
    return data


async def test_log_physical_item_has_no_hash_and_opens_custody_chain(client, auth_full):
    r = await client.post(PATH, data=_form(), headers=auth_full)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {
        "id", "case_id", "item_type", "description", "collected_by",
        "collected_at", "storage_ref", "sha256_hash", "status",
    }
    assert body["sha256_hash"] is None
    assert body["storage_ref"] is None
    assert body["status"] == "logged"

    chain = await client.get(f"{PATH}/{body['id']}/custody", headers=auth_full)
    assert chain.status_code == 200
    assert [e["action"] for e in chain.json()] == ["collected"]


async def test_log_digital_file_computes_and_stores_sha256(client, auth_full):
    content = b"digital evidence payload \x00\x01 " + uuid.uuid4().bytes
    expected = hashlib.sha256(content).hexdigest()
    r = await client.post(
        PATH,
        data=_form(item_type="digital_file", description="disk image"),
        files={"file": ("image.bin", content, "application/octet-stream")},
        headers=auth_full,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sha256_hash"] == expected
    assert body["storage_ref"]

    verify = await client.post(f"{PATH}/{body['id']}/verify", headers=auth_full)
    assert verify.status_code == 200
    v = verify.json()
    assert v["stored_hash"] == expected
    assert v["computed_hash"] == expected
    assert v["match"] is True


async def test_verify_flags_tampering(client, auth_full):
    content = b"original bytes " + uuid.uuid4().bytes
    r = await client.post(
        PATH,
        data=_form(item_type="digital_file"),
        files={"file": ("f.bin", content, "application/octet-stream")},
        headers=auth_full,
    )
    body = r.json()

    # Tamper with the stored blob directly in the vault.
    from app.services import vault

    ref = body["storage_ref"]
    with open(f"{vault.config.vault_dir()}/{ref}", "wb") as fh:
        fh.write(vault._fernet().encrypt(b"tampered bytes"))

    verify = await client.post(f"{PATH}/{body['id']}/verify", headers=auth_full)
    assert verify.status_code == 200
    v = verify.json()
    assert v["match"] is False
    assert v["stored_hash"] != v["computed_hash"]


async def test_verify_409_when_no_digital_file(client, make_item, auth_full):
    item = await make_item()
    r = await client.post(f"{PATH}/{item.id}/verify", headers=auth_full)
    assert r.status_code == 409


async def test_get_item_404(client, auth_full):
    r = await client.get(f"{PATH}/{uuid.uuid4()}", headers=auth_full)
    assert r.status_code == 404


async def test_log_requires_vault_write(client, auth_read):
    r = await client.post(PATH, data=_form(), headers=auth_read)
    assert r.status_code == 403


async def test_get_requires_vault_read(client, make_item, auth_none):
    item = await make_item()
    r = await client.get(f"{PATH}/{item.id}", headers=auth_none)
    assert r.status_code == 403


async def test_endpoints_require_a_token(client, make_item):
    item = await make_item()
    assert (await client.get(f"{PATH}/{item.id}")).status_code == 401
    assert (await client.post(PATH, data=_form())).status_code == 401
