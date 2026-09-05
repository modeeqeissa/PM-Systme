"""transfers.requested_at (docs Section 9.3.6) — the one column missed in 0004

Section 9.3.6: "transfers.requested_at | TIMESTAMPTZ | NOT NULL, DEFAULT
now() | When the transfer was requested". Unlike the service-local
`created_at` bookkeeping column (migration 0003, purely for ordering),
requested_at is an actual SRS-tracked domain fact — set automatically at
request time, never supplied by the client, so it keeps its DB default going
forward (contrast with 0004's placeholder defaults, which were dropped once
existing rows were backfilled).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "transfers",
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade():
    op.drop_column("transfers", "requested_at")
