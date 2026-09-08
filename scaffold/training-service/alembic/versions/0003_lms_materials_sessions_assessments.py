"""materials, sessions, attendance, assessments, assessment_results (docs §9.3.5)

Turns training-service from a course-catalog + certification tracker into a
real LMS: course documents, scheduled sessions with per-officer attendance,
and assessments with graded results (pass/fail derived from
assessments.passing_score at grading time).

All additive — no existing data touched.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "materials",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", sa.Integer, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("file_ref", sa.String(255), nullable=False),
    )
    op.create_index("idx_materials_course", "materials", ["course_id"])

    op.create_table(
        "sessions",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", sa.Integer, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("instructor_officer_id", pg.UUID(as_uuid=True)),
        sa.Column("capacity", sa.Integer),
    )
    op.create_index("idx_sessions_course", "sessions", ["course_id"])
    op.create_index("idx_sessions_scheduled_at", "sessions", ["scheduled_at"])

    op.create_table(
        "attendance",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
    )
    op.create_check_constraint(
        "ck_attendance_status", "attendance",
        "status IN ('registered','attended','absent')",
    )
    # one attendance row per officer per session
    op.create_unique_constraint(
        "uq_attendance_session_officer", "attendance", ["session_id", "officer_id"]
    )
    op.create_index("idx_attendance_session", "attendance", ["session_id"])

    op.create_table(
        "assessments",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", sa.Integer, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("passing_score", sa.Numeric(5, 2), nullable=False),
    )
    op.create_index("idx_assessments_course", "assessments", ["course_id"])

    op.create_table(
        "assessment_results",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assessment_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "taken_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("passed", sa.Boolean, nullable=False),
    )
    op.create_index("idx_assessment_results_assessment", "assessment_results", ["assessment_id"])
    op.create_index("idx_assessment_results_officer", "assessment_results", ["officer_id"])


def downgrade():
    op.drop_table("assessment_results")
    op.drop_table("assessments")
    op.drop_table("attendance")
    op.drop_table("sessions")
    op.drop_table("materials")
