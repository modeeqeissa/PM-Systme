"""Community Policing domain RBAC (FR-COMM-01..04 / docs Section 2.3)

Unlike hr.*/training.cert.*, community.read/write don't exist yet at all —
community-service was never given even unassigned permission codes in 0002.
Adds both codes plus "Community Liaison Officer": docs Section 2.3 — "Logs
community meetings, concerns and tracks follow-up | Full CRUD on Community
Policing domain".

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COMMUNITY_PERMISSIONS = ["community.read", "community.write"]
COMMUNITY_LIAISON_DESCRIPTION = (
    "Community liaison: full CRUD on the Community Policing domain (docs Section 2.3)"
)


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    conn.execute(permissions.insert(), [{"code": c} for c in COMMUNITY_PERMISSIONS])
    perm_id = {
        row.code: row.id
        for row in conn.execute(
            sa.select(permissions.c.id, permissions.c.code).where(
                permissions.c.code.in_(COMMUNITY_PERMISSIONS)
            )
        )
    }

    liaison_id = conn.execute(
        roles.insert()
        .values(name="Community Liaison Officer", description=COMMUNITY_LIAISON_DESCRIPTION)
        .returning(roles.c.id)
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [{"role_id": liaison_id, "permission_id": perm_id[c]} for c in COMMUNITY_PERMISSIONS],
    )


def downgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)
    permissions = sa.Table("permissions", meta, autoload_with=conn)

    liaison_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "Community Liaison Officer")
    ).scalar_one()
    conn.execute(
        role_permissions.delete().where(role_permissions.c.role_id == liaison_id)
    )
    conn.execute(roles.delete().where(roles.c.id == liaison_id))
    conn.execute(
        permissions.delete().where(permissions.c.code.in_(COMMUNITY_PERMISSIONS))
    )
