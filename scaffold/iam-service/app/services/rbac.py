"""Helpers for loading users with their role/permission graph."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Role, User


def _user_query():
    # roles + each role's permissions, eagerly, to build JWT claims / responses.
    return select(User).options(selectinload(User.roles).selectinload(Role.permissions))


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.scalar(_user_query().where(User.id == user_id))


async def get_user_by_badge(session: AsyncSession, badge_number: str) -> User | None:
    return await session.scalar(
        _user_query().where(User.badge_number == badge_number)
    )


def effective_permissions(user: User) -> list[str]:
    codes: set[str] = set()
    for role in user.roles:
        codes.update(p.code for p in role.permissions)
    return sorted(codes)


def role_names(user: User) -> list[str]:
    return sorted(r.name for r in user.roles)
