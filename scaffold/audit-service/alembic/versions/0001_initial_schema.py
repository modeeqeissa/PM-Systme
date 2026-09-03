"""initial audit_db schema — mirrors docs Section 9.3.10

audit_logs is append-only and hash-chained. Append-only is enforced at the
DATABASE level, two independent ways (the same pattern as evidence_db.custody_events):

1. Least privilege: the application connects as ``audit_service_app``, granted
   only SELECT + INSERT on audit_logs. UPDATE/DELETE/TRUNCATE are REVOKEd
   (docs Section 9.3.10 DDL note), so the app role cannot alter history.
2. Triggers: BEFORE UPDATE / BEFORE DELETE on audit_logs raise an exception, so
   even a superuser / the table owner is refused.

Revision ID: 0001
Revises:
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "audit_service_app"
APP_ROLE_DEV_PASSWORD = "audit_app_dev_only"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("service_name", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("prev_hash", sa.CHAR(64), nullable=False),
        sa.Column("record_hash", sa.CHAR(64), nullable=False),
        sa.Column("metadata", pg.JSONB),
    )
    op.create_check_constraint(
        "ck_audit_logs_action",
        "audit_logs",
        "action IN ('create','read','update','delete','export')",
    )
    op.create_index("idx_audit_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("idx_audit_actor", "audit_logs", ["actor_id", "timestamp"])

    op.create_table(
        "consumed_events",
        sa.Column("event_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- append-only triggers (block everyone, incl. owner/superuser) --------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_no_mutate()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs is append-only (FR-AUD-02): % is not permitted', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_logs_block_update BEFORE UPDATE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_no_mutate()"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_block_delete BEFORE DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_no_mutate()"
    )

    # --- least-privilege application role -----------------------------------
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE_DEV_PASSWORD}';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {APP_ROLE}', "
        f"current_database()); END $$;"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")

    op.execute("REVOKE ALL ON audit_logs FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON audit_logs TO {APP_ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO {APP_ROLE}")

    # idempotency ledger: the consumer inserts + reads, never mutates
    op.execute(f"GRANT SELECT, INSERT ON consumed_events TO {APP_ROLE}")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_update ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_no_mutate()")
    op.drop_table("consumed_events")
    op.drop_table("audit_logs")
