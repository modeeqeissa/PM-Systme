"""RS256 JWT issue/verify + JWKS (FR-IAM-02, FR-IAM-08)."""
import datetime as dt
import hashlib
import secrets
import uuid

import jwt
from jwt.algorithms import RSAAlgorithm

from app import config
from app.security import keys


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- refresh / mfa opaque tokens -----------------------------------------
def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- JWTs ---------------------------------------------------------------
def issue_access_token(
    *, user_id: uuid.UUID, badge_number: str, station_id: uuid.UUID,
    roles: list[str], permissions: list[str],
) -> tuple[str, int]:
    ttl = config.ACCESS_TOKEN_TTL_SECONDS
    now = _now()
    payload = {
        "iss": config.JWT_ISSUER,
        "sub": str(user_id),
        "typ": "access",
        "badge_number": badge_number,
        "station_id": str(station_id),
        "roles": roles,
        "permissions": permissions,
        "iat": now,
        "exp": now + dt.timedelta(seconds=ttl),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(
        payload, keys.private_key_pem(), algorithm=config.JWT_ALG,
        headers={"kid": config.JWT_KID},
    )
    return token, ttl


def issue_mfa_token(*, user_id: uuid.UUID, purpose: str = "mfa") -> tuple[str, int]:
    ttl = config.MFA_TOKEN_TTL_SECONDS
    now = _now()
    payload = {
        "iss": config.JWT_ISSUER,
        "sub": str(user_id),
        "typ": purpose,
        "iat": now,
        "exp": now + dt.timedelta(seconds=ttl),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(
        payload, keys.private_key_pem(), algorithm=config.JWT_ALG,
        headers={"kid": config.JWT_KID},
    )
    return token, ttl


def decode_token(token: str, *, expected_typ: str) -> dict:
    """Verify signature + expiry + issuer + token type. Raises jwt exceptions."""
    claims = jwt.decode(
        token,
        keys.public_key_pem(),
        algorithms=[config.JWT_ALG],
        issuer=config.JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "iss"]},
    )
    if claims.get("typ") != expected_typ:
        raise jwt.InvalidTokenError(f"expected {expected_typ} token")
    return claims


def jwks() -> dict:
    jwk = RSAAlgorithm.to_jwk(
        keys.private_key().public_key(), as_dict=True
    )
    jwk.update({"use": "sig", "alg": config.JWT_ALG, "kid": config.JWT_KID})
    return {"keys": [jwk]}
