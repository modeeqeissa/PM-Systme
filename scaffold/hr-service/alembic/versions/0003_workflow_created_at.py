"""service-local created_at on transfers/promotions/leave_requests/
discipline_records/performance_reviews

None of these tables has a domain timestamp in docs Section 9.3.6, and their
PK is a random UUID (gen_random_uuid()) — not chronologically sortable. "list
newest first" (assignment/transfer/leave history, approval queues) needs
*some* ordering column. This is bookkeeping metadata (CLAUDE.md rule 5's
"service-local, non-domain" allowance), not a new SRS-tracked fact — it
doesn't touch what FR-HR-03/05/06/07 actually persist, only in what order the
API returns rows. assignments already has start_date and doesn't need one.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLES = ("transfers", "promotions", "leave_requests", "discipline_records", "performance_reviews")


def upgrade():
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )


def downgrade():
    for table in _TABLES:
        op.drop_column(table, "created_at")
