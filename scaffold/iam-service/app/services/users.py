"""User account management (FR-IAM-06) and password change (FR-IAM-07)."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, User
from app.schemas import UserCreate, UserUpdate
from app.security import passwords
from app.services import audit_events
from app.services import auth as auth_service
from app.services.rbac import get_user


async def load_roles(session: AsyncSession, role_ids: list[int]) -> list[Role]:
    if not role_ids:
        return []
    rows = (
        await session.scalars(select(Role).where(Role.id.in_(set(role_ids))))
    ).all()
    missing = set(role_ids) - {r.id for r in rows}
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown role id(s): {sorted(missing)}"
        )
    return list(rows)


async def create_user(
    session: AsyncSession, payload: UserCreate, *, actor: User
) -> User:
    errors = passwords.policy_errors(payload.password)
    if errors:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Password policy: " + "; ".join(errors)
        )
    roles = await load_roles(session, payload.role_ids)
    user = User(
        badge_number=payload.badge_number,
        email=payload.email,
        password_hash=passwords.hash_password(payload.password),
        full_name=payload.full_name,
        station_id=payload.station_id,
        roles=roles,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Badge number or email already in use"
        )
    created = await get_user(session, user.id)
    audit_events.user_created(session, actor=actor, user=created)  # FR-IAM-06
    return created


async def update_user(
    session: AsyncSession, user_id: uuid.UUID, payload: UserUpdate, *, actor: User
) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")

    previous_status = user.status
    data = payload.model_dump(exclude_unset=True)
    for field in ("full_name", "email", "station_id", "status"):
        if field in data:
            setattr(user, field, data[field])

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")

    if data.get("status") in ("suspended", "deactivated"):
        await auth_service.revoke_all_sessions(session, user.id)

    # FR-IAM-06: emit only on the transition INTO 'deactivated'.
    if user.status == "deactivated" and previous_status != "deactivated":
        audit_events.user_deactivated(
            session, actor=actor, user=user, previous_status=previous_status
        )

    return await get_user(session, user.id)


async def reassign_roles(
    session: AsyncSession, user_id: uuid.UUID, role_ids: list[int], *, actor: User
) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")

    previous_roles = sorted(r.name for r in user.roles)
    user.roles = await load_roles(session, role_ids)
    await session.flush()
    reloaded = await get_user(session, user_id)
    new_roles = sorted(r.name for r in reloaded.roles)

    if set(previous_roles) != set(new_roles):  # FR-IAM-06
        audit_events.user_role_reassigned(
            session,
            actor=actor,
            user=reloaded,
            previous_roles=previous_roles,
            new_roles=new_roles,
        )
    return reloaded


async def change_password(
    session: AsyncSession,
    *,
    target_id: uuid.UUID,
    caller: User,
    caller_can_manage: bool,
    current_password: str | None,
    new_password: str,
) -> None:
    user = await get_user(session, target_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")

    is_self = caller.id == user.id
    if not is_self and not caller_can_manage:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "iam.user.write required to reset another user"
        )
    if is_self and not caller_can_manage:
        if not current_password or not passwords.verify_password(
            current_password, user.password_hash
        ):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "current_password is missing or wrong"
            )

    errors = passwords.policy_errors(new_password)
    if errors:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Password policy: " + "; ".join(errors)
        )

    user.password_hash = passwords.hash_password(new_password)
    await session.flush()
    # FR-IAM-02: password change revokes every active session.
    await auth_service.revoke_all_sessions(session, user.id)
