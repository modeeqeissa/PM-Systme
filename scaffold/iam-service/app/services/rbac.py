"""Helpers for loading users with their role/permission graph."""
import uuid

from sqlalchemy import or_, select
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


async def list_users(
    session: AsyncSession,
    *,
    q: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[User]:
    """Read-only admin listing (FR-IAM-06). `q` is a case-insensitive substring
    match on badge number / full name / email."""
    query = _user_query().order_by(User.badge_number)
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(
                User.badge_number.ilike(like),
                User.full_name.ilike(like),
                User.email.ilike(like),
            )
        )
    if status:
        query = query.where(User.status == status)
    query = query.limit(limit).offset(offset)
    return list((await session.scalars(query)).all())


def effective_permissions(user: User) -> list[str]:
    codes: set[str] = set()
    for role in user.roles:
        codes.update(p.code for p in role.permissions)
    return sorted(codes)


def role_names(user: User) -> list[str]:
    return sorted(r.name for r in user.roles)
