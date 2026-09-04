"""initial community_db schema — mirrors docs Section 9.3.4

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
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "meetings",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("station_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("facilitator_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("meeting_date", sa.Date, nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
    )
    op.create_index("idx_meetings_station", "meetings", ["station_id"])

    op.create_table(
        "concerns",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("meeting_id", pg.UUID(as_uuid=True), sa.ForeignKey("meetings.id")),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
    )
    op.create_check_constraint(
        "ck_concerns_status", "concerns", "status IN ('open','in_progress','resolved')"
    )

    op.create_table(
        "follow_up_actions",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "concern_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("concerns.id"), nullable=False,
        ),
        sa.Column("assigned_to", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_follow_up_actions_status",
        "follow_up_actions",
        "status IN ('pending','overdue','completed')",
    )


def downgrade():
    op.drop_table("follow_up_actions")
    op.drop_table("concerns")
    op.drop_table("meetings")
