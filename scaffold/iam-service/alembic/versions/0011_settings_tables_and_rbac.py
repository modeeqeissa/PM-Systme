"""iam_settings table + per-service settings permission codes (Phase 5)

FR-IAM-07 / SRS §8.1: the password policy moves from env-only to
admin-editable. Adds:
  * iam_settings — key/value overrides for the password policy (env vars
    become the seed/default only).
  * six permission codes — iam.settings.{read,write},
    notification.settings.{read,write}, integration.settings.{read,write} —
    each gating that one service's settings, all granted to "ICT Admin"
    (platform administration, docs §2.3). Deliberately NOT a single coarse
    `settings.write` spanning services, and deliberately NO audit.settings.*
    code — audit-service's retention floor stays env-only per the SRS note.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    "iam.settings.read",
    "iam.settings.write",
    "notification.settings.read",
    "notification.settings.write",
    "integration.settings.read",
    "integration.settings.write",
]


def upgrade():
    op.create_table(
        "iam_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", pg.UUID(as_uuid=True)),
    )

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
    ict_admin_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "ICT Admin")
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [{"role_id": ict_admin_id, "permission_id": perm_id[c]} for c in NEW_PERMISSIONS],
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
    op.drop_table("iam_settings")
