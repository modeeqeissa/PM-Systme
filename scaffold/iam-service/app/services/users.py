"""User account management (FR-IAM-06) and password change (FR-IAM-07)."""
import datetime as dt
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PasswordHistory, Role, User
from app.schemas import UserCreate, UserUpdate
from app.security import passwords
from app.services import audit_events
from app.services import auth as auth_service
from app.services import settings
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
    changed: list[str] = []
    for field in ("full_name", "email", "station_id", "status"):
        if field in data and data[field] != getattr(user, field):
            setattr(user, field, data[field])
            changed.append(field)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")

    if data.get("status") in ("suspended", "deactivated"):
        await auth_service.revoke_all_sessions(session, user.id)

    # FR-IAM-06: emit only on the transition INTO 'deactivated'.
    deactivated = user.status == "deactivated" and previous_status != "deactivated"
    if deactivated:
        audit_events.user_deactivated(
            session, actor=actor, user=user, previous_status=previous_status
        )
    # Any other admin change to a profile/scoping field (esp. station_id) is
    # itself an audit-worthy IAM write — the deactivation transition already
    # has its own richer event, so don't double-report a status-only PATCH.
    other = [f for f in changed if not (f == "status" and deactivated)]
    if other:
        audit_events.user_updated(session, actor=actor, user=user, fields=other)

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

    # FR-IAM-07: no reuse of the last N passwords (current + history).
    history_count = settings.get("password_history_count")
    if history_count > 0:
        recent = await _recent_password_hashes(session, user, history_count)
        if passwords.is_reused(new_password, recent):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Password policy: must not reuse any of the last "
                f"{history_count} passwords",
            )

    # keep the outgoing hash in history, then rotate.
    session.add(
        PasswordHistory(user_id=user.id, password_hash=user.password_hash)
    )
    user.password_hash = passwords.hash_password(new_password)
    user.password_changed_at = dt.datetime.now(dt.timezone.utc)
    await session.flush()
    await _trim_password_history(session, user.id, history_count)
    # FR-IAM-02: password change revokes every active session.
    await auth_service.revoke_all_sessions(session, user.id)
    # FR-IAM-06: audit the change (admin reset vs. self-service).
    audit_events.user_password_changed(
        session, actor=caller, user=user, by_admin=not is_self
    )


async def _recent_password_hashes(
    session: AsyncSession, user: User, keep: int
) -> list[str]:
    """The current password hash plus the most recent history hashes, capped at
    `keep` total — the set a new password must not collide with."""
    rows = (
        await session.scalars(
            select(PasswordHistory.password_hash)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.changed_at.desc(), PasswordHistory.id.desc())
            .limit(max(keep - 1, 0))
        )
    ).all()
    return [user.password_hash, *rows]


async def _trim_password_history(
    session: AsyncSession, user_id: uuid.UUID, keep: int
) -> None:
    """Delete history rows beyond the most recent `keep - 1` (the current
    password lives on users.password_hash, so history only needs keep-1)."""
    survivors = (
        await session.scalars(
            select(PasswordHistory.id)
            .where(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.changed_at.desc(), PasswordHistory.id.desc())
            .limit(max(keep - 1, 0))
        )
    ).all()
    stmt = delete(PasswordHistory).where(PasswordHistory.user_id == user_id)
    if survivors:
        stmt = stmt.where(PasswordHistory.id.notin_(survivors))
    await session.execute(stmt)
