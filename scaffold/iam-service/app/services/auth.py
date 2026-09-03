"""Authentication flows: login -> MFA -> token issue, refresh, logout.

FR-IAM-01 (password + mandatory TOTP), FR-IAM-02 (<=15 min access tokens +
rotating refresh tokens, revocable), FR-IAM-05 (lockout).
"""
import datetime as dt
import uuid

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.models import Session, User
from app.schemas import MfaChallenge, MfaEnrollment, TokenPair
from app.security import mfa, passwords, tokens
from app.services.rbac import effective_permissions, get_user, get_user_by_badge, role_names


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def _issue_pair(
    session: AsyncSession, user: User, device_info: str | None
) -> TokenPair:
    access_token, ttl = tokens.issue_access_token(
        user_id=user.id,
        badge_number=user.badge_number,
        station_id=user.station_id,
        roles=role_names(user),
        permissions=effective_permissions(user),
    )
    raw_refresh = tokens.new_opaque_token()
    session.add(
        Session(
            user_id=user.id,
            refresh_token_hash=tokens.hash_token(raw_refresh),
            expires_at=_now() + dt.timedelta(seconds=config.REFRESH_TOKEN_TTL_SECONDS),
            device_info=device_info,
        )
    )
    await session.flush()
    return TokenPair(access_token=access_token, refresh_token=raw_refresh, expires_in=ttl)


async def login(
    session: AsyncSession, badge_number: str, password: str
) -> MfaChallenge:
    user = await get_user_by_badge(session, badge_number)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Account {user.status}")

    if user.failed_login_count >= config.MAX_FAILED_LOGINS:
        raise HTTPException(status.HTTP_423_LOCKED, "Account locked - contact ICT/security")

    if not passwords.verify_password(password, user.password_hash):
        user.failed_login_count += 1
        # Commit the counter now: the request ends in an error, and get_session
        # would otherwise roll the increment back, so lockout would never trip.
        await session.commit()
        if user.failed_login_count >= config.MAX_FAILED_LOGINS:
            # FR-IAM-05: also notify ICT/security (audit/notification wiring TODO).
            raise HTTPException(
                status.HTTP_423_LOCKED, "Account locked after too many failed attempts"
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.failed_login_count:
        user.failed_login_count = 0
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    await session.flush()

    mfa_token, ttl = tokens.issue_mfa_token(user_id=user.id)
    return MfaChallenge(
        mfa_token=mfa_token, mfa_enrolled=user.mfa_enrolled, expires_in=ttl
    )


async def enroll_mfa(
    session: AsyncSession, user_id: uuid.UUID, *, allow_reenroll: bool
) -> MfaEnrollment:
    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    if user.mfa_secret is not None and not allow_reenroll:
        raise HTTPException(status.HTTP_409_CONFLICT, "TOTP already enrolled")

    secret = mfa.new_secret()
    user.mfa_secret = mfa.encrypt_secret(secret)
    await session.flush()
    return MfaEnrollment(
        secret=secret, otpauth_uri=mfa.provisioning_uri(secret, user.badge_number)
    )


async def verify_mfa(
    session: AsyncSession, mfa_token: str, code: str, device_info: str | None
) -> TokenPair:
    try:
        claims = tokens.decode_token(mfa_token, expected_typ="mfa")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired mfa_token")

    user = await get_user(session, uuid.UUID(claims["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired mfa_token")
    if user.mfa_secret is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOTP not enrolled")

    if not mfa.verify_code(mfa.decrypt_secret(user.mfa_secret), code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong TOTP code")

    return await _issue_pair(session, user, device_info)


async def refresh(
    session: AsyncSession, refresh_token: str, device_info: str | None
) -> TokenPair:
    token_hash = tokens.hash_token(refresh_token)
    row = await session.scalar(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    if row is None or row.revoked_at is not None or row.expires_at <= _now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    row.revoked_at = _now()  # rotate
    user = await get_user(session, row.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    await session.flush()
    return await _issue_pair(session, user, device_info or row.device_info)


async def logout(session: AsyncSession, refresh_token: str) -> None:
    token_hash = tokens.hash_token(refresh_token)
    row = await session.scalar(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        await session.flush()


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
