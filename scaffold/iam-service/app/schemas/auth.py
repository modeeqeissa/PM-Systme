from typing import Literal

from pydantic import BaseModel


class LoginRequest(BaseModel):
    badge_number: str
    password: str


class MfaChallenge(BaseModel):
    mfa_token: str
    mfa_enrolled: bool
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MfaEnrollment(BaseModel):
    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str
    device_info: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class Jwks(BaseModel):
    keys: list[dict]
