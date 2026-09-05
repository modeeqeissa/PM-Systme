"""officers.supervisor_id — direct supervisor (corrected docs §9.3.6)

Nullable self-referencing FK. §9.3.6 calls it a "logical FK → officers.id",
but it's same-table so a real FK constraint is used (no cross-service
concern). Supports FR-COMM-04's supervisor-escalation / notification path.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "officers",
        sa.Column("supervisor_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_officers_supervisor_id",
        "officers",
        "officers",
        ["supervisor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_officers_supervisor", "officers", ["supervisor_id"])


def downgrade():
    op.drop_index("idx_officers_supervisor", table_name="officers")
    op.drop_constraint("fk_officers_supervisor_id", "officers", type_="foreignkey")
    op.drop_column("officers", "supervisor_id")
