"""Auth flow: login -> MFA -> tokens, refresh rotation, logout, lockout, JWKS."""
import jwt
import pyotp
import pytest

from tests.conftest import auth

LOGIN = "/api/v1/auth/login"
ENROLL = "/api/v1/auth/mfa/enroll"
VERIFY = "/api/v1/auth/mfa/verify"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


async def _login(client, seeded):
    r = await client.post(
        LOGIN, json={"badge_number": seeded.badge_number, "password": seeded.password}
    )
    return r


async def _full_login(client, seeded):
    r = await _login(client, seeded)
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]
    code = pyotp.TOTP(seeded.mfa_secret).now()
    r = await client.post(VERIFY, json={"mfa_token": mfa_token, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


async def test_login_returns_mfa_challenge(client, make_user):
    user = await make_user()
    r = await _login(client, user)
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_enrolled"] is True
    assert body["token_type"] == "bearer"
    assert isinstance(body["mfa_token"], str) and body["expires_in"] > 0
    assert "access_token" not in body  # no tokens before the 2nd factor


async def test_login_wrong_password_401(client, make_user):
    user = await make_user()
    r = await client.post(
        LOGIN, json={"badge_number": user.badge_number, "password": "wrong"}
    )
    assert r.status_code == 401


async def test_login_unknown_badge_401(client):
    r = await client.post(LOGIN, json={"badge_number": "nobody", "password": "x"})
    assert r.status_code == 401


async def test_login_suspended_account_403(client, make_user):
    user = await make_user(status="suspended")
    r = await _login(client, user)
    assert r.status_code == 403


async def test_account_locks_after_max_failed_attempts(client, make_user):
    user = await make_user()
    for _ in range(5):
        await client.post(
            LOGIN, json={"badge_number": user.badge_number, "password": "wrong"}
        )
    # correct password now, but the account is locked
    r = await _login(client, user)
    assert r.status_code == 423


async def test_mfa_verify_issues_token_pair(client, make_user):
    user = await make_user()
    tok = await _full_login(client, user)
    assert tok["token_type"] == "bearer"
    assert 0 < tok["expires_in"] <= 900
    claims = jwt.decode(tok["access_token"], options={"verify_signature": False})
    assert claims["sub"] == str(user.id)
    assert claims["typ"] == "access"
    assert claims["station_id"] == str(user.station_id)


async def test_mfa_verify_wrong_code_401(client, make_user):
    user = await make_user()
    r = await _login(client, user)
    r = await client.post(
        VERIFY, json={"mfa_token": r.json()["mfa_token"], "code": "000000"}
    )
    assert r.status_code == 401


async def test_mfa_verify_rejects_tampered_mfa_token(client, make_user):
    user = await make_user()
    r = await client.post(
        VERIFY, json={"mfa_token": "not.a.jwt", "code": "000000"}
    )
    assert r.status_code == 401


async def test_enroll_with_mfa_token_when_not_enrolled(client, make_user):
    user = await make_user(with_mfa=False)
    r = await _login(client, user)
    assert r.json()["mfa_enrolled"] is False
    mfa_token = r.json()["mfa_token"]
    r = await client.post(ENROLL, headers=auth(mfa_token))
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://totp/")
    # now the second factor works
    r = await client.post(LOGIN, json={"badge_number": user.badge_number, "password": user.password})
    code = pyotp.TOTP(secret).now()
    r = await client.post(VERIFY, json={"mfa_token": r.json()["mfa_token"], "code": code})
    assert r.status_code == 200


async def test_enroll_conflict_when_already_enrolled_with_mfa_token(client, make_user):
    user = await make_user(with_mfa=True)
    r = await _login(client, user)
    r = await client.post(ENROLL, headers=auth(r.json()["mfa_token"]))
    assert r.status_code == 409


async def test_enroll_requires_a_token(client):
    r = await client.post(ENROLL)
    assert r.status_code == 401


async def test_refresh_rotates_and_revokes_old_token(client, make_user):
    user = await make_user()
    tok = await _full_login(client, user)
    r = await client.post(REFRESH, json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != tok["refresh_token"]
    # old refresh token is now dead
    r = await client.post(REFRESH, json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401
    # new one still works
    r = await client.post(REFRESH, json={"refresh_token": new["refresh_token"]})
    assert r.status_code == 200


async def test_refresh_unknown_token_401(client):
    r = await client.post(REFRESH, json={"refresh_token": "nope"})
    assert r.status_code == 401


async def test_logout_revokes_session_and_is_idempotent(client, make_user):
    user = await make_user()
    tok = await _full_login(client, user)
    r = await client.post(LOGOUT, json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 204
    r = await client.post(REFRESH, json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401
    # logging out again is still 204
    r = await client.post(LOGOUT, json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 204


async def test_password_change_revokes_sessions(client, make_user):
    user = await make_user()
    tok = await _full_login(client, user)
    r = await client.post(
        f"/api/v1/users/{user.id}/password",
        headers=auth(tok["access_token"]),
        json={"current_password": user.password, "new_password": "An0ther!Passw0rd"},
    )
    assert r.status_code == 204
    r = await client.post(REFRESH, json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401


async def test_jwks_matches_token_signature(client, make_user):
    user = await make_user()
    tok = await _full_login(client, user)
    jwks = (await client.get("/api/v1/auth/jwks")).json()
    assert jwks["keys"] and jwks["keys"][0]["kty"] == "RSA"
    key = jwt.PyJWKSet.from_dict(jwks).keys[0]
    claims = jwt.decode(
        tok["access_token"], key.key, algorithms=["RS256"], issuer="pmp-iam-service"
    )
    assert claims["sub"] == str(user.id)


@pytest.mark.parametrize("field", ["badge_number", "password"])
async def test_login_validation_requires_fields(client, field):
    body = {"badge_number": "x", "password": "y"}
    del body[field]
    r = await client.post(LOGIN, json=body)
    assert r.status_code == 422
