"""Shared FastAPI dependencies: db session + JWT/RBAC check.

RBAC is enforced from the start by validating the RS256 access token issued by
iam-service: the signature is checked against iam-service's JWKS (cached, see
``app/security/jwks.py``), issuer + expiry are verified, and the required
permission code must appear in the token's ``permissions`` claim (CLAUDE.md
rule 4). No placeholder header.

Missing / malformed / expired token -> 401. Valid token without the permission
-> 403.
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config
from app.db import get_session  # re-exported for routers
from app.security.jwks import JwksError, jwks_cache

__all__ = ["get_session", "require_permission", "get_token_claims"]

_bearer = HTTPBearer(
    scheme_name="bearerAuth",
    auto_error=False,
    description="RS256 access token issued by iam-service (/api/v1/auth/mfa/verify)",
)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing or invalid access token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_token_claims(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if cred is None or not cred.credentials:
        raise _UNAUTHENTICATED
    token = cred.credentials
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        key = await jwks_cache.get_key(kid)
        claims = jwt.decode(
            token,
            key,
            algorithms=[config.JWT_ALG],
            issuer=config.jwt_issuer(),
            options={"require": ["exp", "iat", "sub"]},
        )
    except (jwt.PyJWTError, JwksError):
        raise _UNAUTHENTICATED
    if claims.get("typ") != "access":
        raise _UNAUTHENTICATED
    return claims


def require_permission(code: str):
    """Dependency factory: 403 unless the token's ``permissions`` claim holds ``code``."""

    async def _check(claims: dict = Depends(get_token_claims)) -> dict:
        if code not in (claims.get("permissions") or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="RBAC scope denied"
            )
        return claims

    return _check
