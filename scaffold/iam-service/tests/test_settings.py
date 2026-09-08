"""/iam-settings — admin-editable password policy (FR-IAM-07, Phase 5).

The IAM_PASSWORD_* env vars are the seed/default; a PATCH overrides them at
runtime. "ICT Admin" holds iam.settings.{read,write} (migration 0011).
"""
import pytest
from sqlalchemy import select

from app.events.models import OutboxEvent
from tests.conftest import SessionLocal, auth

SETTINGS = "/api/v1/iam-settings"
USERS = "/api/v1/users"


async def _events(event_type: str) -> list[OutboxEvent]:
    async with SessionLocal() as s:
        return list(
            (await s.scalars(select(OutboxEvent).where(OutboxEvent.event_type == event_type))).all()
        )


async def test_get_returns_effective_defaults(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.get(SETTINGS, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"values", "overridden"}
    assert body["overridden"] == []
    # env defaults (app.config)
    assert body["values"]["password_min_length"] == 12
    assert body["values"]["password_require_symbol"] in (True, False)


async def test_get_requires_settings_read(client, make_user, access_token_for):
    user = await make_user(roles=["Patrol Officer"])
    token = await access_token_for(user)
    assert (await client.get(SETTINGS, headers=auth(token))).status_code == 403


async def test_patch_requires_settings_write(client, make_user, access_token_for):
    user = await make_user(roles=["Patrol Officer"])
    token = await access_token_for(user)
    r = await client.patch(SETTINGS, headers=auth(token), json={"password_min_length": 8})
    assert r.status_code == 403


async def test_patch_overrides_and_persists(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)

    r = await client.patch(
        SETTINGS,
        headers=auth(token),
        json={"password_min_length": 8, "password_require_symbol": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["values"]["password_min_length"] == 8
    assert r.json()["values"]["password_require_symbol"] is False
    assert set(r.json()["overridden"]) == {"password_min_length", "password_require_symbol"}

    # a fresh GET (new request, cache already reloaded) shows the same
    g = await client.get(SETTINGS, headers=auth(token))
    assert g.json()["values"]["password_min_length"] == 8

    evs = await _events("IamSettingsUpdated")
    assert len(evs) == 1
    assert evs[0].body["payload"]["changed"] == {"password_min_length": "8", "password_require_symbol": "false"}


async def test_patch_unknown_key_400(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.patch(SETTINGS, headers=auth(token), json={"password_min_lenght": 8})
    assert r.status_code in (400, 422)  # extra=forbid -> 422 at the schema layer


async def test_patch_invalid_value_400(client, make_user, access_token_for):
    admin = await make_user(roles=["ICT Admin"])
    token = await access_token_for(admin)
    r = await client.patch(SETTINGS, headers=auth(token), json={"password_min_length": 0})
    assert r.status_code in (400, 422)


async def test_lowering_min_length_makes_a_previously_rejected_password_accepted(
    client, make_user, access_token_for
):
    """The Phase 5 behaviour check: change the setting, confirm the underlying
    behaviour actually changes — not just that the row updated."""
    admin = await make_user(roles=["ICT Admin"])
    admin_token = await access_token_for(admin)
    user = await make_user(roles=["Patrol Officer"])
    user_token = await access_token_for(user)

    short_new = "Ab1!cdef"  # 8 chars, complexity OK, but < default min length 12

    rejected = await client.post(
        f"{USERS}/{user.id}/password",
        headers=auth(user_token),
        json={"current_password": user.password, "new_password": short_new},
    )
    assert rejected.status_code == 400
    assert "at least 12" in rejected.json()["detail"]

    # admin lowers the minimum
    patched = await client.patch(
        SETTINGS, headers=auth(admin_token), json={"password_min_length": 8}
    )
    assert patched.status_code == 200

    accepted = await client.post(
        f"{USERS}/{user.id}/password",
        headers=auth(user_token),
        json={"current_password": user.password, "new_password": short_new},
    )
    assert accepted.status_code in (200, 204), accepted.text
