"""initial training_db schema — mirrors docs Section 9.3.5

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
        "courses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("validity_months", sa.SmallInteger, nullable=False),
        sa.Column("mandatory", sa.Boolean, nullable=False, server_default="false"),
    )

    op.create_table(
        "certifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "course_id", sa.Integer, sa.ForeignKey("courses.id"), nullable=False
        ),
    )

    op.create_table(
        "officer_certifications",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "certification_id", sa.Integer,
            sa.ForeignKey("certifications.id"), nullable=False,
        ),
        sa.Column("issued_date", sa.Date, nullable=False),
        sa.Column("expires_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "ck_officer_certifications_status",
        "officer_certifications",
        "status IN ('active','expiring_soon','expired')",
    )
    op.create_index(
        "idx_officer_certifications_officer", "officer_certifications", ["officer_id"]
    )
    op.create_index(
        "idx_officer_certifications_expires", "officer_certifications", ["expires_date"]
    )


def downgrade():
    op.drop_table("officer_certifications")
    op.drop_table("certifications")
    op.drop_table("courses")
