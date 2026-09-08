"""integration_settings — admin-editable external-system-log retention (Phase 5)

INTEGRATION_GATEWAY_LOG_RETENTION_DAYS becomes the seed/default only; an admin
can override it at runtime via PATCH /integration-settings, gated on
integration.settings.write (permission codes seeded by iam migration 0011).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", pg.UUID(as_uuid=True)),
    )


def downgrade():
    op.drop_table("integration_settings")
