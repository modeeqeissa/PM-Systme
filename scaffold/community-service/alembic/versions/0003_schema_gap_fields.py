"""close the §9.3.4 schema gap — attendee_summary, descriptions, raised_by

The corrected docs Section 9.3.4 adds:
* meetings.attendee_summary   TEXT NULLABLE
* concerns.description        TEXT NOT NULL
* concerns.raised_by          VARCHAR(150) NULLABLE
* follow_up_actions.description TEXT NOT NULL

The two NOT NULL text columns land on tables that already hold rows in dev,
so they're added with a placeholder server_default, backfilled, then the
default is dropped — the app must supply a real value from here on (same
backfill-then-drop pattern as hr-service migration 0004).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_PLACEHOLDER = "(unspecified — backfilled by migration 0003)"


def upgrade():
    op.add_column("meetings", sa.Column("attendee_summary", sa.Text(), nullable=True))
    op.add_column("concerns", sa.Column("raised_by", sa.String(150), nullable=True))

    op.add_column(
        "concerns",
        sa.Column("description", sa.Text(), nullable=False, server_default=_PLACEHOLDER),
    )
    op.alter_column("concerns", "description", server_default=None)

    op.add_column(
        "follow_up_actions",
        sa.Column("description", sa.Text(), nullable=False, server_default=_PLACEHOLDER),
    )
    op.alter_column("follow_up_actions", "description", server_default=None)


def downgrade():
    op.drop_column("follow_up_actions", "description")
    op.drop_column("concerns", "description")
    op.drop_column("concerns", "raised_by")
    op.drop_column("meetings", "attendee_summary")
