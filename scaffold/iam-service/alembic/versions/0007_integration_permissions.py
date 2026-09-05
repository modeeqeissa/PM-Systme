"""Integration Gateway domain RBAC (FR-INT-01..05 / docs Section 2.3)

Adds integration.read/write (didn't exist at all, same gap as community.*
before 0006) and grants them to the existing "ICT Admin" role — docs Section
2.3: "System Administrator / ICT Unit — Manages users, roles, system
configuration, integrations | Full administrative access". No new role is
created since ICT Admin already exists (seeded in 0002).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

INTEGRATION_PERMISSIONS = ["integration.read", "integration.write"]


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    conn.execute(permissions.insert(), [{"code": c} for c in INTEGRATION_PERMISSIONS])
    perm_id = {
        row.code: row.id
        for row in conn.execute(
            sa.select(permissions.c.id, permissions.c.code).where(
                permissions.c.code.in_(INTEGRATION_PERMISSIONS)
            )
        )
    }

    ict_admin_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "ICT Admin")
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [{"role_id": ict_admin_id, "permission_id": perm_id[c]} for c in INTEGRATION_PERMISSIONS],
    )


def downgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)
    permissions = sa.Table("permissions", meta, autoload_with=conn)

    ict_admin_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "ICT Admin")
    ).scalar_one()
    perm_ids = [
        row.id
        for row in conn.execute(
            sa.select(permissions.c.id).where(
                permissions.c.code.in_(INTEGRATION_PERMISSIONS)
            )
        )
    ]
    conn.execute(
        role_permissions.delete().where(
            role_permissions.c.role_id == ict_admin_id,
            role_permissions.c.permission_id.in_(perm_ids),
        )
    )
    conn.execute(
        permissions.delete().where(permissions.c.code.in_(INTEGRATION_PERMISSIONS))
    )
