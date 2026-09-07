"""client_sync_id on arrests + statements (field-originated idempotency)

CLAUDE.md rule 6 / TD-006: field officers record statements and arrests in the
field (docs §2.3), so those endpoints need the same offline-safe dedupe
`POST /incidents` already has. Adds a nullable, UNIQUE client_sync_id — the
Idempotency-Key header value — matching incidents.client_sync_id exactly. A
NULL means the write carried no key (still allowed; the header is optional on
these two, unlike incidents).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("arrests", "statements"):
        op.add_column(
            table, sa.Column("client_sync_id", pg.UUID(as_uuid=True), nullable=True)
        )
        op.create_unique_constraint(f"uq_{table}_client_sync_id", table, ["client_sync_id"])


def downgrade():
    for table in ("arrests", "statements"):
        op.drop_constraint(f"uq_{table}_client_sync_id", table, type_="unique")
        op.drop_column(table, "client_sync_id")
