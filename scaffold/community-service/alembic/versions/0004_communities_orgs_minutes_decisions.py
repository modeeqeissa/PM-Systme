"""communities, organizations, meeting_minutes, decisions; meetings.community_id

Corrected docs Section 9.3.4 adds the richer community-policing model:
* communities      — a named neighbourhood/group per station
* organizations    — partner orgs, optionally tied to a community
* meetings.community_id — nullable FK to the community a meeting was held with
* meeting_minutes  — one formal minutes record per meeting (UNIQUE meeting_id)
* decisions        — formal resolutions made at a meeting, with their own
                     pending/implemented/abandoned lifecycle

All additive. `meetings.community_id` is nullable so existing meeting rows
need no backfill.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "communities",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("station_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text),
    )
    op.create_index("idx_communities_station", "communities", ["station_id"])

    op.create_table(
        "organizations",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column(
            "community_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("communities.id", ondelete="SET NULL"),
        ),
        sa.Column("contact_name", sa.String(150)),
        sa.Column("contact_phone", sa.String(30)),
    )
    op.create_index("idx_organizations_community", "organizations", ["community_id"])

    op.add_column(
        "meetings",
        sa.Column(
            "community_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("communities.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("idx_meetings_community", "meetings", ["community_id"])

    op.create_table(
        "meeting_minutes",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "meeting_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=False),
    )

    op.create_table(
        "decisions",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "meeting_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_decisions_status", "decisions",
        "status IN ('pending','implemented','abandoned')",
    )
    op.create_index("idx_decisions_meeting", "decisions", ["meeting_id"])


def downgrade():
    op.drop_table("decisions")
    op.drop_table("meeting_minutes")
    op.drop_index("idx_meetings_community", "meetings")
    op.drop_column("meetings", "community_id")
    op.drop_table("organizations")
    op.drop_table("communities")
