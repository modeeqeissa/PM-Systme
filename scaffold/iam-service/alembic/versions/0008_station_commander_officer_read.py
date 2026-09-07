"""grant hr.officer.read to the Station Commander role (station-scoped)

Migration 0004 gave Station Commander hr.transfer.read / hr.leave.read /
hr.leave.approve — approve transfers/leave "at station level" (docs §2.3) —
but not hr.officer.read, so a commander could act on their station's
transfer/leave queue without being able to see the officers those requests
belong to. That is a gap, not a real restriction: §2.3's "read on
station-level dashboard" reasonably covers seeing one's own station's roster.

This grants the (already-defined, 0004) `hr.officer.read` code to the role.
It stays read-only — full HR CRUD (hr.officer.write etc.) remains HR-Officer
only — and hr-service scopes the result to the caller's station unless they
also hold hr.officer.write (the force-wide marker).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_ROLE = "Station Commander"
_PERM = "hr.officer.read"


def _ids(conn):
    role_id = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = :n"), {"n": _ROLE}
    ).scalar_one()
    perm_id = conn.execute(
        sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": _PERM}
    ).scalar_one()
    return role_id, perm_id


def upgrade():
    conn = op.get_bind()
    role_id, perm_id = _ids(conn)
    conn.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "VALUES (:r, :p) ON CONFLICT DO NOTHING"
        ),
        {"r": role_id, "p": perm_id},
    )


def downgrade():
    conn = op.get_bind()
    role_id, perm_id = _ids(conn)
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id = :r AND permission_id = :p"
        ),
        {"r": role_id, "p": perm_id},
    )
