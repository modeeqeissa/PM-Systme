"""external_system_logs.created_at — retention needs a creation timestamp (FR-AUD-04).

Per docs §9.6 integration logs are 180-day operational data with a real purge
job (app.services.retention). "Older than N days" is measured from row
creation, so the table needs a created_at it did not previously carry.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "external_system_logs",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_external_system_logs_created_at", "external_system_logs", ["created_at"]
    )


def downgrade():
    op.drop_index(
        "ix_external_system_logs_created_at", table_name="external_system_logs"
    )
    op.drop_column("external_system_logs", "created_at")
