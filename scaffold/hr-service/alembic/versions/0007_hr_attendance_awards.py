"""hr_attendance + awards (docs §9.3.6 revised)

* hr_attendance — one row per officer per day (present/absent/late/excused),
  optional clock in/out times. UNIQUE(officer_id, date).
* awards — commendations/recognition, the positive counterpart to
  discipline_records.

Both additive; no existing data touched.

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
        "hr_attendance",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("clock_in", sa.DateTime(timezone=True)),
        sa.Column("clock_out", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_check_constraint(
        "ck_hr_attendance_status", "hr_attendance",
        "status IN ('present','absent','late','excused')",
    )
    op.create_unique_constraint(
        "uq_hr_attendance_officer_date", "hr_attendance", ["officer_id", "date"]
    )
    op.create_index("idx_hr_attendance_officer", "hr_attendance", ["officer_id"])
    op.create_index("idx_hr_attendance_date", "hr_attendance", ["date"])

    op.create_table(
        "awards",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "officer_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("officers.id"), nullable=False,
        ),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("awarded_date", sa.Date, nullable=False),
        # logical FK -> officers.id (approving/awarding officer)
        sa.Column("awarded_by", pg.UUID(as_uuid=True), sa.ForeignKey("officers.id")),
    )
    op.create_index("idx_awards_officer", "awards", ["officer_id"])


def downgrade():
    op.drop_table("awards")
    op.drop_table("hr_attendance")
