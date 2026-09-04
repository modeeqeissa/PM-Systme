"""initial integration_db schema — mirrors docs Section 9.3.9

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
        "integration_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("system_name", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
    )

    op.create_table(
        "external_system_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("system_name", sa.String(50), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("correlation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("response_status", sa.Integer),
    )
    op.create_check_constraint(
        "ck_external_system_logs_direction",
        "external_system_logs",
        "direction IN ('inbound','outbound')",
    )
    op.create_index(
        "idx_external_system_logs_corr", "external_system_logs", ["correlation_id"]
    )
    op.create_index(
        "idx_external_system_logs_system", "external_system_logs", ["system_name"]
    )


def downgrade():
    op.drop_table("external_system_logs")
    op.drop_table("integration_configs")
