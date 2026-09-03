"""Configurable roles & permissions (FR-IAM-03), zero-permission default (NFR-SEC-03)."""
import uuid

from tests.conftest import auth

ROLES = "/api/v1/roles"
PERMS = "/api/v1/permissions"


async def test_seeded_permissions_are_listed(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.get(PERMS, headers=auth(token))
    assert r.status_code == 200
    codes = {p["code"] for p in r.json()}
    assert {"case.read", "case.write", "iam.user.write", "audit.read"} <= codes


async def test_list_roles_requires_role_read(client, make_user, access_token_for):
    user = await make_user(roles=["Patrol Officer"])
    token = await access_token_for(user)
    assert (await client.get(ROLES, headers=auth(token))).status_code == 403


async def test_new_role_starts_with_zero_permissions(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.post(
        ROLES, headers=auth(token), json={"name": "Front Desk", "description": "intake"}
    )
    assert r.status_code == 201
    assert r.json()["permissions"] == []
    role_id = r.json()["id"]

    # duplicate name -> 409
    r = await client.post(ROLES, headers=auth(token), json={"name": "Front Desk"})
    assert r.status_code == 409

    # grant a couple of permissions
    r = await client.put(
        f"{ROLES}/{role_id}/permissions",
        headers=auth(token),
        json={"codes": ["case.read", "dashboard.view"]},
    )
    assert r.status_code == 200
    assert sorted(r.json()["permissions"]) == ["case.read", "dashboard.view"]


async def test_set_permissions_unknown_code_404(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    role_id = (await client.post(ROLES, headers=auth(token), json={"name": "Temp"})).json()["id"]
    r = await client.put(
        f"{ROLES}/{role_id}/permissions",
        headers=auth(token),
        json={"codes": ["case.read", "does.not.exist"]},
    )
    assert r.status_code == 404


async def test_assign_roles_to_user_changes_effective_permissions(
    client, make_user, access_token_for
):
    admin = await make_user(roles=["ICT Admin"])
    admin_token = await access_token_for(admin)
    target = await make_user()  # no roles -> no permissions
    target_token = await access_token_for(target)

    me = await client.get("/api/v1/users/me", headers=auth(target_token))
    assert me.json()["permissions"] == []

    r = await client.put(
        f"/api/v1/users/{target.id}/roles",
        headers=auth(admin_token),
        json={"role_ids": [2, 4]},  # Patrol Officer + Station Commander
    )
    assert r.status_code == 200
    assert set(r.json()["roles"]) == {"Patrol Officer", "Station Commander"}
    assert "case.approve" in r.json()["permissions"]


async def test_assign_unknown_role_404(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    target = await make_user()
    r = await client.put(
        f"/api/v1/users/{target.id}/roles",
        headers=auth(token),
        json={"role_ids": [999]},
    )
    assert r.status_code == 404


async def test_assign_roles_requires_role_write(client, make_user, access_token_for):
    user = await make_user(roles=["Investigator"])  # has case.* but not iam.role.write
    token = await access_token_for(user)
    r = await client.put(
        f"/api/v1/users/{user.id}/roles", headers=auth(token), json={"role_ids": [2]}
    )
    assert r.status_code == 403
