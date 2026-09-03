"""End-to-end: authenticate against a live iam-service, then call case-service.

Exercises the whole chain — iam-service issues an RS256 token via login -> MFA
-> verify, case-service fetches iam-service's JWKS, verifies the signature, and
enforces the `permissions` claim.
"""
import uuid

from tests.conftest import bearer, iam_access_token


async def test_iam_issued_token_grants_and_denies_case_access(client, make_case, iam_server):
    case = await make_case(status="open")

    # E2E-RW (Patrol Officer) holds case.read + case.write.
    rw_token = iam_access_token("E2E-RW")
    r = await client.get(f"/api/v1/cases/{case.id}", headers=bearer(rw_token))
    assert r.status_code == 200
    assert r.json()["id"] == str(case.id)

    r = await client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "investigating"},
        headers=bearer(rw_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "investigating"

    # E2E-NONE (Auditor) holds neither case permission -> 403 on a read.
    none_token = iam_access_token("E2E-NONE")
    r = await client.get(f"/api/v1/cases/{case.id}", headers=bearer(none_token))
    assert r.status_code == 403

    # E2E-RO (Station Commander) has case.read but not case.write -> 403 on write.
    ro_token = iam_access_token("E2E-RO")
    r = await client.get(f"/api/v1/cases/{case.id}", headers=bearer(ro_token))
    assert r.status_code == 200
    r = await client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "closed"},
        headers=bearer(ro_token),
    )
    assert r.status_code == 403


async def test_forged_and_missing_tokens_are_rejected(client, make_case, iam_server):
    case = await make_case()
    assert (await client.get(f"/api/v1/cases/{case.id}")).status_code == 401
    assert (
        await client.get(f"/api/v1/cases/{case.id}", headers=bearer("not.a.jwt"))
    ).status_code == 401

    # A well-formed RS256 token signed by the wrong key must not verify.
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "iss": "pmp-iam-service",
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "permissions": ["case.read", "case.write"],
            "iat": 1_760_000_000,
            "exp": 4_102_444_800,
        },
        rogue,
        algorithm="RS256",
        headers={"kid": "iam-dev-1"},
    )
    r = await client.get(f"/api/v1/cases/{case.id}", headers=bearer(forged))
    assert r.status_code == 401


async def test_jwks_is_cached_across_requests(client, make_case, auth_rw):
    from app.security.jwks import jwks_cache

    jwks_cache.clear()
    case = await make_case()

    r = await client.get(f"/api/v1/cases/{case.id}", headers=auth_rw)
    assert r.status_code == 200
    fetches_after_first = jwks_cache.refresh_count
    assert fetches_after_first >= 1  # first request populated the cache

    for _ in range(5):
        r = await client.get(f"/api/v1/cases/{case.id}", headers=auth_rw)
        assert r.status_code == 200
    assert jwks_cache.refresh_count == fetches_after_first  # served from cache, no re-fetch
