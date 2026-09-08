"""HR attendance + awards RBAC (docs §9.3.6 revised / FR-HR)

The corrected docs §9.3.6 adds `hr_attendance` (daily present/absent/late/
excused) and `awards` (the positive counterpart to discipline_records). Adds
the read/write permission codes for both and grants all four to "HR Officer"
("Full CRUD on the HR domain", docs §2.3) — the same pattern migration 0004
used for the rest of the HR domain.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    "hr.attendance.read",
    "hr.attendance.write",
    "hr.award.read",
    "hr.award.write",
]


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    conn.execute(permissions.insert(), [{"code": c} for c in NEW_PERMISSIONS])
    perm_id = {
        row.code: row.id
        for row in conn.execute(
            sa.select(permissions.c.id, permissions.c.code).where(
                permissions.c.code.in_(NEW_PERMISSIONS)
            )
        )
    }
    hr_officer_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "HR Officer")
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [{"role_id": hr_officer_id, "permission_id": perm_id[c]} for c in NEW_PERMISSIONS],
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": NEW_PERMISSIONS},
    )
    conn.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": NEW_PERMISSIONS},
    )
