"""/auth/* — login, MFA, token lifecycle, JWKS (FR-IAM-01, 02, 08)."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import EnrollmentContext, get_enrollment_context, get_session
from app.schemas import (
    Jwks,
    LoginRequest,
    MfaChallenge,
    MfaEnrollment,
    MfaVerifyRequest,
    RefreshRequest,
    TokenPair,
)
from app.security import tokens
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=MfaChallenge)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    return await svc.login(session, body.badge_number, body.password)


@router.post("/mfa/enroll", response_model=MfaEnrollment)
async def enroll_mfa(
    ctx: EnrollmentContext = Depends(get_enrollment_context),
    session: AsyncSession = Depends(get_session),
):
    return await svc.enroll_mfa(session, ctx.user_id, allow_reenroll=ctx.allow_reenroll)


@router.post("/mfa/verify", response_model=TokenPair)
async def verify_mfa(
    body: MfaVerifyRequest, session: AsyncSession = Depends(get_session)
):
    return await svc.verify_mfa(session, body.mfa_token, body.code, body.device_info)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    return await svc.refresh(session, body.refresh_token, device_info=None)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    await svc.logout(session, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jwks", response_model=Jwks)
async def jwks():
    return tokens.jwks()
