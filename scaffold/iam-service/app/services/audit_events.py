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


def user_updated(
    session: AsyncSession, *, actor: User, user: User, fields: list[str]
) -> None:
    """An admin PATCH that changed profile/scoping fields (full_name, email,
    station_id, status) other than the deactivation transition — FR-IAM-06
    "reassign user accounts ... every action written to the audit log".
    station_id in particular is RBAC-scoping data (CLAUDE.md rule 3)."""
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="UserUpdated",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "user_id": str(user.id),
            "badge_number": user.badge_number,
            "fields": sorted(fields),
            "station_id": str(user.station_id),
            "status": user.status,
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


def user_password_changed(
    session: AsyncSession, *, actor: User, user: User, by_admin: bool
) -> None:
    """FR-IAM-06 — a password reset is a security-relevant IAM write. `actor`
    is the admin who reset it, or the user themselves on a self-service
    change; `by_admin` records which."""
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="UserPasswordChanged",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "user_id": str(user.id),
            "badge_number": user.badge_number,
            "by_admin": by_admin,
        },
    )


def role_created(session: AsyncSession, *, actor: User, role) -> None:
    """FR-IAM-03/06 — a new role is a permission-definition change."""
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="RoleCreated",
        aggregate_type="role",
        aggregate_id=role.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"role_id": role.id, "name": role.name},
    )


def role_permissions_changed(
    session: AsyncSession, *, actor: User, role, previous: list[str], new: list[str]
) -> None:
    """FR-IAM-03/06 — changing what a role grants is high-impact; carries the
    before/after code sets, like UserRoleReassigned."""
    actor_id, actor_role = _actor(actor)
    enqueue(
        session,
        event_type="RolePermissionsChanged",
        aggregate_type="role",
        aggregate_id=role.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "role_id": role.id,
            "name": role.name,
            "previous_permissions": sorted(previous),
            "new_permissions": sorted(new),
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
