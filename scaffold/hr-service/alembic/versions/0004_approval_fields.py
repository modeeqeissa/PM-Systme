"""close the hr_db schema gap fixed in docs Section 9.3.6

The SRS was corrected to add the date/approver columns the FR-HR-03..07 prose
always described but 9.3.6 never persisted (see the 0003 docstring / project
memory). This migration catches the schema up:

* transfers:            + effective_date (nullable), approved_by (nullable)
* promotions:            + effective_date (NOT NULL), approved_by (NOT NULL)
* leave_requests:        + start_date, end_date (NOT NULL), approved_by (nullable)
* discipline_records:    + incident_date (NOT NULL), description (NOT NULL),
                           outcome (nullable)
* performance_reviews:   + comments (nullable)

approved_by is a real in-database FK to officers.id (unlike cross-service
references elsewhere, which are logical-only) — per the SRS wording "set on
approval", it's populated only when a transfer/leave request is approved,
left NULL on rejection. promotions has no separate approval step, so
effective_date/approved_by are supplied at recording time instead and are
NOT NULL there.

The three NOT-NULL additions land on tables that may already have rows (dev
data predating this migration): each is added with a placeholder
server_default, existing rows backfilled, then the default is dropped so the
application must supply real values from here on.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_PLACEHOLDER_DESCRIPTION = "(unspecified — backfilled by migration 0004)"


def upgrade():
    # --- transfers: nullable, set only on approval -----------------------
    op.add_column("transfers", sa.Column("effective_date", sa.Date, nullable=True))
    op.add_column(
        "transfers",
        sa.Column(
            "approved_by", pg.UUID(as_uuid=True), sa.ForeignKey("officers.id"), nullable=True
        ),
    )

    # --- promotions: NOT NULL, supplied at recording time -----------------
    op.add_column(
        "promotions",
        sa.Column(
            "effective_date", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
    )
    op.add_column(
        "promotions",
        sa.Column(
            "approved_by", pg.UUID(as_uuid=True), sa.ForeignKey("officers.id"), nullable=True
        ),
    )
    # No universally-valid placeholder UUID exists for a pre-existing row's
    # approver; the promoted officer standing in for their own (unknown,
    # pre-migration) approver is the only FK-safe backfill available.
    op.execute("UPDATE promotions SET approved_by = officer_id WHERE approved_by IS NULL")
    op.alter_column("promotions", "approved_by", nullable=False)
    op.alter_column("promotions", "effective_date", server_default=None)

    # --- leave_requests: dates NOT NULL, approved_by set only on approval -
    op.add_column(
        "leave_requests",
        sa.Column("start_date", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")),
    )
    op.add_column(
        "leave_requests",
        sa.Column("end_date", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")),
    )
    op.add_column(
        "leave_requests",
        sa.Column(
            "approved_by", pg.UUID(as_uuid=True), sa.ForeignKey("officers.id"), nullable=True
        ),
    )
    op.alter_column("leave_requests", "start_date", server_default=None)
    op.alter_column("leave_requests", "end_date", server_default=None)

    # --- discipline_records: incident_date/description NOT NULL -----------
    op.add_column(
        "discipline_records",
        sa.Column(
            "incident_date", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
    )
    op.add_column(
        "discipline_records",
        sa.Column(
            "description",
            sa.Text,
            nullable=False,
            server_default=_PLACEHOLDER_DESCRIPTION,
        ),
    )
    op.add_column("discipline_records", sa.Column("outcome", sa.String(100), nullable=True))
    op.alter_column("discipline_records", "incident_date", server_default=None)
    op.alter_column("discipline_records", "description", server_default=None)

    # --- performance_reviews: comments, nullable ---------------------------
    op.add_column("performance_reviews", sa.Column("comments", sa.Text, nullable=True))


def downgrade():
    op.drop_column("performance_reviews", "comments")

    op.drop_column("discipline_records", "outcome")
    op.drop_column("discipline_records", "description")
    op.drop_column("discipline_records", "incident_date")

    op.drop_column("leave_requests", "approved_by")
    op.drop_column("leave_requests", "end_date")
    op.drop_column("leave_requests", "start_date")

    op.drop_column("promotions", "approved_by")
    op.drop_column("promotions", "effective_date")

    op.drop_column("transfers", "approved_by")
    op.drop_column("transfers", "effective_date")
