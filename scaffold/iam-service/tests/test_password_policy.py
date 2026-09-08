"""FR-IAM-07: configurable password policy — complexity, history, expiry."""
import datetime as dt
import uuid

from sqlalchemy import func, select

from app import config
from app.models import PasswordHistory, User
from tests.conftest import SessionLocal, auth

USERS = "/api/v1/users"
PW = "Sup3rSecret!pw"  # the default make_user password (satisfies the policy)


async def _self_change(client, user, token, new_password, current=None):
    return await client.post(
        f"{USERS}/{user.id}/password",
        headers=auth(token),
        json={"current_password": current or user.password, "new_password": new_password},
    )


# --- complexity is configurable, not hardcoded --------------------------
async def test_complexity_rules_toggle_off(client, make_user, access_token_for, monkeypatch):
    user = await make_user()
    token = await access_token_for(user)
    # default policy rejects a password with no symbol
    r = await _self_change(client, user, token, "NoSymbol12345")
    assert r.status_code == 400 and "symbol" in r.json()["detail"]

    monkeypatch.setattr(config, "PASSWORD_REQUIRE_SYMBOL", False)
    r = await _self_change(client, user, token, "NoSymbol12345")
    assert r.status_code == 204


async def test_min_length_is_configurable(client, make_user, access_token_for, monkeypatch):
    user = await make_user()
    token = await access_token_for(user)
    monkeypatch.setattr(config, "PASSWORD_MIN_LENGTH", 20)
    r = await _self_change(client, user, token, "Sh0rt!butvalidchars")  # 19 chars
    assert r.status_code == 400 and "at least 20" in r.json()["detail"]


# --- history: no reuse of the last N -----------------------------------
async def test_cannot_reuse_current_or_recent_passwords(
    client, make_user, access_token_for, monkeypatch
):
    monkeypatch.setattr(config, "PASSWORD_HISTORY_COUNT", 3)
    user = await make_user()
    token = await access_token_for(user)

    # reusing the *current* password is rejected
    r = await _self_change(client, user, token, PW)
    assert r.status_code == 400 and "reuse" in r.json()["detail"]

    # walk through 3 distinct new passwords
    pwds = ["Alpha!12345678", "Bravo!12345678", "Charlie!1234567"]
    cur = PW
    for p in pwds:
        r = await _self_change(client, user, token, p, current=cur)
        assert r.status_code == 204, r.text
        cur = p

    # the oldest of those 3 is still within the window -> rejected
    r = await _self_change(client, user, token, pwds[0], current=cur)
    assert r.status_code == 400 and "reuse" in r.json()["detail"]

    # PW is now 4 changes back (outside history of 3) -> allowed again
    r = await _self_change(client, user, token, PW, current=cur)
    assert r.status_code == 204

    # history stays trimmed to at most COUNT-1 rows
    async with SessionLocal() as s:
        n = await s.scalar(
            select(func.count())
            .select_from(PasswordHistory)
            .where(PasswordHistory.user_id == user.id)
        )
    assert n <= config.PASSWORD_HISTORY_COUNT - 1


async def test_history_count_zero_disables_the_check(
    client, make_user, access_token_for, monkeypatch
):
    monkeypatch.setattr(config, "PASSWORD_HISTORY_COUNT", 0)
    user = await make_user()
    token = await access_token_for(user)
    # immediately reuse the current password — allowed when history is off
    r = await _self_change(client, user, token, PW)
    assert r.status_code == 204


# --- expiry: reset-on-next-login, login is NOT blocked ----------------
async def _backdate_password(user_id: uuid.UUID, days: int) -> None:
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        u.password_changed_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        await s.commit()


async def test_expired_password_flags_but_does_not_block_login(
    client, make_user, access_token_for, monkeypatch
):
    monkeypatch.setattr(config, "PASSWORD_MAX_AGE_DAYS", 30)
    user = await make_user(with_mfa=True)
    await _backdate_password(user.id, 45)

    # login still succeeds and carries the flag
    login = await client.post(
        "/api/v1/auth/login", json={"badge_number": user.badge_number, "password": user.password}
    )
    assert login.status_code == 200
    assert login.json()["password_expired"] is True

    # MFA verify still issues a token pair, also flagged
    import pyotp

    code = pyotp.TOTP(user.mfa_secret).now()
    verify = await client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": login.json()["mfa_token"], "code": code}
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["password_expired"] is True

    # /users/me reports it too, and the token works (reset endpoint is reachable)
    me = await client.get("/api/v1/users/me", headers=auth(body["access_token"]))
    assert me.status_code == 200 and me.json()["password_expired"] is True

    # changing the password clears it
    r = await _self_change(client, user, body["access_token"], "Fr3sh!password123")
    assert r.status_code == 204
    async with SessionLocal() as s:
        u = await s.get(User, user.id)
        assert not config.PASSWORD_MAX_AGE_DAYS or (
            dt.datetime.now(dt.timezone.utc) - u.password_changed_at.replace(tzinfo=dt.timezone.utc)
        ) < dt.timedelta(minutes=1)


async def test_expiry_disabled_by_default(client, make_user, access_token_for):
    user = await make_user()
    await _backdate_password(user.id, 3650)
    token = await access_token_for(user)
    me = await client.get("/api/v1/users/me", headers=auth(token))
    assert me.json()["password_expired"] is False
