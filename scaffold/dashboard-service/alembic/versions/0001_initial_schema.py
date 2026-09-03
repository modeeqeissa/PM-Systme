"""initial dashboard_db read models — docs Section 9.3.7 (CQRS projections)

Plain tables (not Postgres materialised views) so the Kafka consumer can refresh
them incrementally per event. All are rebuildable by replaying the event log.

Revision ID: 0001
Revises:
Create Date: 2026-09-03
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
        "dash_consumed_events",
        sa.Column("event_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "dash_case",
        sa.Column("case_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("station_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_type", sa.String(50)),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "mv_station_case_kpis",
        sa.Column("station_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("open_cases", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("closed_cases", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("arrests_recorded", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "sum_age_days", sa.Numeric(18, 6), nullable=False, server_default="0"
        ),
    )

    op.create_table(
        "mv_crime_trends",
        sa.Column("station_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("month", sa.Date, primary_key=True),
        sa.Column("incident_type", sa.String(50), primary_key=True),
        sa.Column("count", sa.BigInteger, nullable=False, server_default="0"),
    )

    op.create_table(
        "mv_evidence_integrity",
        sa.Column("evidence_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_logged", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "pending_transfer_ack_count",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "hash_mismatch_count", sa.BigInteger, nullable=False, server_default="0"
        ),
    )


def downgrade():
    op.drop_table("mv_evidence_integrity")
    op.drop_table("mv_crime_trends")
    op.drop_table("mv_station_case_kpis")
    op.drop_table("dash_case")
    op.drop_table("dash_consumed_events")
