"""transactional outbox for evidence-service

outbox_events holds domain events written in the same transaction as the state
change (SRS §3.4 / §9.4); app.events.relay drains them to Kafka. The
least-privilege application role gets SELECT/INSERT/UPDATE here (the relay marks
rows published) - but still no rights on custody_events beyond INSERT/SELECT.

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

APP_ROLE = "evidence_service_app"


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

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON outbox_events TO {APP_ROLE}")
    op.execute(
        f"GRANT USAGE, SELECT ON SEQUENCE outbox_events_id_seq TO {APP_ROLE}"
    )


def downgrade():
    op.drop_index("idx_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")
