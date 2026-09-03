import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.rbac import Role

Status = Literal["active", "suspended", "deactivated"]


class UserCreate(BaseModel):
    badge_number: str = Field(max_length=20)
    email: EmailStr | None = None
    password: str
    full_name: str = Field(max_length=150)
    station_id: uuid.UUID
    role_ids: list[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    station_id: uuid.UUID | None = None
    status: Status | None = None


class User(BaseModel):
    id: uuid.UUID
    badge_number: str
    email: EmailStr | None = None
    full_name: str
    station_id: uuid.UUID
    status: Status
    failed_login_count: int
    mfa_enrolled: bool
    roles: list[Role] = Field(default_factory=list)
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_model(cls, user) -> "User":
        return cls(
            id=user.id,
            badge_number=user.badge_number,
            email=user.email,
            full_name=user.full_name,
            station_id=user.station_id,
            status=user.status,
            failed_login_count=user.failed_login_count,
            mfa_enrolled=user.mfa_enrolled,
            roles=[Role.from_model(r) for r in user.roles],
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class CurrentUser(BaseModel):
    id: uuid.UUID
    badge_number: str
    email: EmailStr | None = None
    full_name: str
    station_id: uuid.UUID
    status: Status
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(cls, user) -> "CurrentUser":
        perms: set[str] = set()
        for role in user.roles:
            perms.update(p.code for p in role.permissions)
        return cls(
            id=user.id,
            badge_number=user.badge_number,
            email=user.email,
            full_name=user.full_name,
            station_id=user.station_id,
            status=user.status,
            roles=sorted(r.name for r in user.roles),
            permissions=sorted(perms),
        )


class PasswordChange(BaseModel):
    current_password: str | None = None
    new_password: str
