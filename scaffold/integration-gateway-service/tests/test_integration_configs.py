async def test_four_systems_are_seeded(client, auth_ict):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    assert r.status_code == 200
    names = {c["system_name"] for c in r.json()}
    assert names == {"CAD", "NCDB", "COURTS", "JAIL"}
    assert all(c["enabled"] for c in r.json())


async def test_get_one_config(client, auth_ict):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    config_id = r.json()[0]["id"]
    r = await client.get(f"/api/v1/integration-configs/{config_id}", headers=auth_ict)
    assert r.status_code == 200
    assert r.json()["id"] == config_id


async def test_get_unknown_config_404(client, auth_ict):
    r = await client.get("/api/v1/integration-configs/999999", headers=auth_ict)
    assert r.status_code == 404


async def test_list_requires_integration_read(client, auth_none):
    r = await client.get("/api/v1/integration-configs", headers=auth_none)
    assert r.status_code == 403


async def test_toggle_kill_switch(client, auth_ict):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    cad = next(c for c in r.json() if c["system_name"] == "CAD")

    r = await client.patch(
        f"/api/v1/integration-configs/{cad['id']}",
        json={"enabled": False},
        headers=auth_ict,
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = await client.get(f"/api/v1/integration-configs/{cad['id']}", headers=auth_ict)
    assert r.json()["enabled"] is False


async def test_toggle_requires_integration_write(client, auth_ict, auth_none):
    r = await client.get("/api/v1/integration-configs", headers=auth_ict)
    config_id = r.json()[0]["id"]
    r = await client.patch(
        f"/api/v1/integration-configs/{config_id}",
        json={"enabled": False},
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_toggle_unknown_config_404(client, auth_ict):
    r = await client.patch(
        "/api/v1/integration-configs/999999", json={"enabled": False}, headers=auth_ict
    )
    assert r.status_code == 404


async def test_configs_require_auth(client):
    r = await client.get("/api/v1/integration-configs")
    assert r.status_code == 401
