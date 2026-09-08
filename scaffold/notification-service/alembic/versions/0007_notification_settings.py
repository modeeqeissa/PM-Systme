"""notification_settings — admin-editable retention window (Phase 5)

NOTIFICATION_RETENTION_DAYS becomes the seed/default only; an admin can
override it at runtime via PATCH /notification-settings, gated on
notification.settings.write (iam migration 0011).

Note: the delivery-*failure* retention (`_FAILED_RETENTION_DAYS` = 365, §9.6)
is deliberately NOT made editable here — same reason audit-service's floor is
env-only: it is a compliance value, not an operational knob.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", pg.UUID(as_uuid=True)),
    )


def downgrade():
    op.drop_table("notification_settings")
