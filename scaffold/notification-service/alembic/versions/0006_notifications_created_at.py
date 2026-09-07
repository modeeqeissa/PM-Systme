"""notifications.created_at — retention needs a creation timestamp (FR-AUD-04).

Per docs §9.6 notifications are 90-day operational data with a real purge job
(app.services.retention). "Older than N days" is measured from row creation,
so the table needs a created_at it did not previously carry.

Backfills existing rows to now() (they are recent dev/test data) so the NOT
NULL default holds.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notifications",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade():
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_column("notifications", "created_at")
