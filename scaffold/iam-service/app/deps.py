"""Shared FastAPI dependencies: db session, bearer auth, RBAC checks.

Unlike the other services (which trust a gateway-injected header until iam-service
exists), iam-service *is* the token authority: it verifies its own RS256 access
tokens here directly.
"""
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.security import tokens
from app.services.rbac import effective_permissions, get_user

__all__ = [
    "get_session",
    "get_current_user",
    "require_permission",
    "get_enrollment_context",
    "EnrollmentContext",
]

_bearer = HTTPBearer(auto_error=False)


def _credential(cred: HTTPAuthorizationCredentials | None) -> str:
    if cred is None or not cred.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return cred.credentials


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = _credential(cred)
    try:
        claims = tokens.decode_token(token, expected_typ="access")
    except jwt.PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user(session, uuid.UUID(claims["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or unknown")
    return user


def require_permission(code: str):
    """Dependency factory: 403 unless the caller's roles grant ``code`` (FR-IAM-03)."""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if code not in effective_permissions(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires permission {code}")
        return user

    return _check


@dataclass
class EnrollmentContext:
    user_id: uuid.UUID
    allow_reenroll: bool  # True when authorised with a full access token


async def get_enrollment_context(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> EnrollmentContext:
    """Accept either a full access token (re-enrol allowed) or the login mfa_token."""
    token = _credential(cred)
    try:
        claims = tokens.decode_token(token, expected_typ="access")
        return EnrollmentContext(uuid.UUID(claims["sub"]), allow_reenroll=True)
    except jwt.PyJWTError:
        pass
    try:
        claims = tokens.decode_token(token, expected_typ="mfa")
    except jwt.PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return EnrollmentContext(uuid.UUID(claims["sub"]), allow_reenroll=False)
