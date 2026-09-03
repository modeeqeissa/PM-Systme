"""User account management (FR-IAM-06) + password policy (FR-IAM-07)."""
import uuid

from tests.conftest import auth

USERS = "/api/v1/users"


async def test_me_returns_roles_and_effective_permissions(client, make_user, access_token_for):
    user = await make_user(roles=["Investigator"])
    token = await access_token_for(user)
    r = await client.get(f"{USERS}/me", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(user.id)
    assert body["roles"] == ["Investigator"]
    assert "case.write" in body["permissions"]
    assert "evidence.custody.write" in body["permissions"]


async def test_me_requires_token(client):
    assert (await client.get(f"{USERS}/me")).status_code == 401


async def test_me_rejects_garbage_token(client):
    assert (await client.get(f"{USERS}/me", headers=auth("garbage"))).status_code == 401


async def test_create_user_requires_permission(client, make_user, access_token_for):
    weak = await make_user(roles=["Patrol Officer"])
    token = await access_token_for(weak)
    r = await client.post(
        USERS,
        headers=auth(token),
        json={
            "badge_number": "NEW-1",
            "password": "Cr3ate!dUserpw",
            "full_name": "New Officer",
            "station_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 403


async def test_admin_creates_user_with_roles(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.post(
        USERS,
        headers=auth(token),
        json={
            "badge_number": "NEW-2",
            "email": "new2@police.example",
            "password": "Cr3ate!dUserpw",
            "full_name": "New Officer 2",
            "station_id": str(uuid.uuid4()),
            "role_ids": [2],  # Patrol Officer
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["badge_number"] == "NEW-2"
    assert body["mfa_enrolled"] is False
    assert body["failed_login_count"] == 0
    assert [role["name"] for role in body["roles"]] == ["Patrol Officer"]
    assert "password" not in body and "password_hash" not in body


async def test_create_user_duplicate_badge_409(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    payload = {
        "badge_number": "DUP-1",
        "password": "Cr3ate!dUserpw",
        "full_name": "Dup",
        "station_id": str(uuid.uuid4()),
    }
    assert (await client.post(USERS, headers=auth(token), json=payload)).status_code == 201
    assert (await client.post(USERS, headers=auth(token), json=payload)).status_code == 409


async def test_create_user_weak_password_400(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.post(
        USERS,
        headers=auth(token),
        json={
            "badge_number": "WEAK-1",
            "password": "short",
            "full_name": "Weak",
            "station_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 400


async def test_get_user_404(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.get(f"{USERS}/{uuid.uuid4()}", headers=auth(token))
    assert r.status_code == 404


async def test_patch_user_deactivate_revokes_sessions(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    admin_token = await access_token_for(admin)
    victim = await make_user()
    # give the victim a live session
    import pyotp

    lr = await client.post(
        "/api/v1/auth/login",
        json={"badge_number": victim.badge_number, "password": victim.password},
    )
    vr = await client.post(
        "/api/v1/auth/mfa/verify",
        json={
            "mfa_token": lr.json()["mfa_token"],
            "code": pyotp.TOTP(victim.mfa_secret).now(),
        },
    )
    refresh = vr.json()["refresh_token"]

    r = await client.patch(
        f"{USERS}/{victim.id}", headers=auth(admin_token), json={"status": "deactivated"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "deactivated"
    # session is gone
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_self_password_change_needs_current_password(client, make_user, access_token_for):
    user = await make_user()
    token = await access_token_for(user)
    r = await client.post(
        f"{USERS}/{user.id}/password",
        headers=auth(token),
        json={"new_password": "Br4nd!newpasswd"},
    )
    assert r.status_code == 401  # missing current_password

    r = await client.post(
        f"{USERS}/{user.id}/password",
        headers=auth(token),
        json={"current_password": user.password, "new_password": "Br4nd!newpasswd"},
    )
    assert r.status_code == 204


async def test_admin_resets_another_password_without_current(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    other = await make_user()
    r = await client.post(
        f"{USERS}/{other.id}/password",
        headers=auth(token),
        json={"new_password": "R3set!byadminpw"},
    )
    assert r.status_code == 204


async def test_non_admin_cannot_reset_others_password(client, make_user, access_token_for):
    user = await make_user()
    token = await access_token_for(user)
    other = await make_user()
    r = await client.post(
        f"{USERS}/{other.id}/password",
        headers=auth(token),
        json={"new_password": "R3set!attemptpw"},
    )
    assert r.status_code == 403
