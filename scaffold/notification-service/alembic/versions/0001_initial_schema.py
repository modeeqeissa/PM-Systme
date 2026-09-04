"""initial notification_db schema — mirrors docs Section 9.3.8

Phase 1 stub: schema only, no endpoints yet.

Revision ID: 0001
Revises:
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_templates",
        sa.Column("code", sa.String(50), primary_key=True),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("recipient_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column(
            "template_code", sa.String(50),
            sa.ForeignKey("notification_templates.code"), nullable=False,
        ),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
    )
    op.create_check_constraint(
        "ck_notifications_channel",
        "notifications",
        "channel IN ('email','sms','push','in_app')",
    )
    op.create_check_constraint(
        "ck_notifications_status",
        "notifications",
        "status IN ('queued','sent','delivered','failed')",
    )
    op.create_index(
        "idx_notifications_recipient", "notifications", ["recipient_user_id"]
    )


def downgrade():
    op.drop_table("notifications")
    op.drop_table("notification_templates")
