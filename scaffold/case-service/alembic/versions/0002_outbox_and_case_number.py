"""transactional outbox + sequential case numbers

* outbox_events — domain events written in the same transaction as the state
  change (SRS §3.4 / §9.4), drained to Kafka by app.events.relay.
* case_number_seq — backs the unique, sequential case number (FR-CASE-02).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("topic", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("aggregate_type", sa.String(60), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("body", pg.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "idx_outbox_unpublished",
        "outbox_events",
        ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.execute("CREATE SEQUENCE IF NOT EXISTS case_number_seq")


def downgrade():
    op.execute("DROP SEQUENCE IF EXISTS case_number_seq")
    op.drop_index("idx_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")
