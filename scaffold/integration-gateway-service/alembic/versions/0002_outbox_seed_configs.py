"""transactional outbox + seed the four named external systems (docs §9.3.9)

outbox_events holds domain events written in the same transaction as the
integration-gateway write (SRS §3.4 / §9.4); app.events.relay drains them to
Kafka and audit-service consumes them into audit_logs (CLAUDE.md rule 3).

docs Section 9.3.9's example system_name values (CAD, NCDB, COURTS, JAIL) are
seeded here as the fixed catalog of named external systems (FR-INT-01..04) —
there is no endpoint to create arbitrary new ones, since the SRS names these
four specifically and integration_configs' only other column is the
enabled kill switch.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SYSTEM_NAMES = ["CAD", "NCDB", "COURTS", "JAIL"]


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

    conn = op.get_bind()
    meta = sa.MetaData()
    configs = sa.Table("integration_configs", meta, autoload_with=conn)
    conn.execute(configs.insert(), [{"system_name": s, "enabled": True} for s in SYSTEM_NAMES])


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM integration_configs WHERE system_name = ANY(:names)"),
        {"names": SYSTEM_NAMES},
    )
    op.drop_index("idx_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")
