"""initial hr_db schema — mirrors docs Section 9.3.6

Phase 1 stub: schema only, no endpoints yet. discipline_records carries a
confidentiality_level that will drive extra RBAC/audit scrutiny in Phase 1.

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

_UUID_PK = dict(primary_key=True, server_default=sa.text("gen_random_uuid()"))


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "units",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("station_id", pg.UUID(as_uuid=True), nullable=False),
    )
    op.create_index("idx_units_station", "units", ["station_id"])

    op.create_table(
        "officers",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("badge_number", sa.String(20), nullable=False, unique=True),
        sa.Column("rank", sa.String(50), nullable=False),
        sa.Column(
            "unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id"), nullable=False
        ),
        sa.Column("hire_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "ck_officers_status",
        "officers",
        "status IN ('active','on_leave','suspended','retired')",
    )
    op.create_index("idx_officers_unit", "officers", ["unit_id"])

    op.create_table(
        "assignments",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column(
            "unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id"), nullable=False
        ),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date),
    )

    op.create_table(
        "transfers",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column("from_unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id")),
        sa.Column("to_unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_transfers_status", "transfers", "status IN ('pending','approved','rejected')"
    )

    op.create_table(
        "promotions",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column("previous_rank", sa.String(50), nullable=False),
        sa.Column("new_rank", sa.String(50), nullable=False),
    )

    op.create_table(
        "leave_requests",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column("leave_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_leave_requests_status",
        "leave_requests",
        "status IN ('pending','approved','rejected')",
    )

    op.create_table(
        "discipline_records",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column(
            "confidentiality_level", sa.String(20),
            nullable=False, server_default="restricted",
        ),
    )

    op.create_table(
        "performance_reviews",
        sa.Column("id", pg.UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column(
            "reviewer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("score", sa.Numeric(4, 2), nullable=False),
    )


def downgrade():
    op.drop_table("performance_reviews")
    op.drop_table("discipline_records")
    op.drop_table("leave_requests")
    op.drop_table("promotions")
    op.drop_table("transfers")
    op.drop_table("assignments")
    op.drop_table("officers")
    op.drop_table("units")
