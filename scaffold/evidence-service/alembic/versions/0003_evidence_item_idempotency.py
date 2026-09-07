"""client_sync_id on evidence_items (field-originated idempotency)

CLAUDE.md rule 6 / TD-006: a field officer logs evidence from the PWA, where
the request (a multipart upload) may be queued offline and replayed on
reconnect. A nullable, UNIQUE client_sync_id — the Idempotency-Key header
value — lets the replay return the original item (200) without re-hashing or
re-storing the file. NULL = the write carried no key (the header is optional).

evidence_items is not append-only (only custody_events is), so ALTER is fine.

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
    op.add_column(
        "evidence_items",
        sa.Column("client_sync_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_evidence_items_client_sync_id", "evidence_items", ["client_sync_id"]
    )


def downgrade():
    op.drop_constraint(
        "uq_evidence_items_client_sync_id", "evidence_items", type_="unique"
    )
    op.drop_column("evidence_items", "client_sync_id")
