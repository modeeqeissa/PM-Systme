"""iam-service domain events for the audit trail (TD-003, FR-IAM-05/06).

Each helper enqueues an outbox row inside the caller's DB transaction, so the
admin action / lockout and its event commit atomically. app.events.relay
publishes them; audit-service consumes them into audit_logs.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import enqueue
from app.models import User


def _actor(user: User) -> tuple[str, str]:
    return str(user.id), ",".join(sorted(r.name for r in user.roles)) or "unknown"


def user_created(session: AsyncSession, *, actor: User, user: User) -> None:
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="UserCreated",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "user_id": str(user.id),
            "badge_number": user.badge_number,
            "full_name": user.full_name,
            "station_id": str(user.station_id),
            "roles": sorted(r.name for r in user.roles),
        },
    )


def user_deactivated(
    session: AsyncSession, *, actor: User, user: User, previous_status: str
) -> None:
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="UserDeactivated",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "user_id": str(user.id),
            "badge_number": user.badge_number,
            "previous_status": previous_status,
            "new_status": user.status,
        },
    )


def user_role_reassigned(
    session: AsyncSession,
    *,
    actor: User,
    user: User,
    previous_roles: list[str],
    new_roles: list[str],
) -> None:
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="UserRoleReassigned",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "user_id": str(user.id),
            "badge_number": user.badge_number,
            "previous_roles": sorted(previous_roles),
            "new_roles": sorted(new_roles),
        },
    )


def account_locked_out(
    session: AsyncSession, *, user: User, failed_login_count: int
) -> None:
    """No admin actor — an automated security action triggered by the account's
    own failed attempts. actor_id is the locked account itself."""
    enqueue(
        session,
        event_type="AccountLockedOut",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=str(user.id),
        actor_role="system",
        payload={
            "user_id": str(user.id),
            "badge_number": user.badge_number,
            "failed_login_count": failed_login_count,
        },
    )
