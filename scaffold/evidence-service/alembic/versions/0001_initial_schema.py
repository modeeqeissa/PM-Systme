"""initial evidence_db schema — mirrors docs Section 9.3.3

Enforces the FR-EVID-03 append-only guarantee for custody_events at the
DATABASE level, two independent ways:

1. Least privilege: the application connects as ``evidence_service_app``, which
   is granted only SELECT + INSERT on custody_events. UPDATE/DELETE are REVOKEd
   (per the Section 9.3.3 DDL note), so the app role literally cannot modify a
   custody entry.
2. Triggers: BEFORE UPDATE / BEFORE DELETE on custody_events raise an exception,
   so even a superuser / the table owner is refused - the app code is not the
   only thing standing between a custody record and modification.

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

APP_ROLE = "evidence_service_app"
APP_ROLE_DEV_PASSWORD = "evidence_app_dev_only"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()

    op.create_table(
        "evidence_items",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("case_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("collected_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_ref", sa.String(255)),
        sa.Column("sha256_hash", sa.CHAR(64)),
        sa.Column("status", sa.String(30), nullable=False, server_default="logged"),
    )
    op.create_check_constraint(
        "ck_evidence_items_status",
        "evidence_items",
        "status IN ('logged','in_analysis','in_court','disposed')",
    )
    op.create_index("idx_evidence_items_case", "evidence_items", ["case_id"])

    op.create_table(
        "custody_events",
        # BIGSERIAL per Section 9.3.3 -> sequence custody_events_id_seq
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "evidence_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("evidence_items.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("from_officer", pg.UUID(as_uuid=True)),
        sa.Column("to_officer", pg.UUID(as_uuid=True)),
        sa.Column("acknowledgement_signature", sa.String(255)),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_custody_events_action",
        "custody_events",
        "action IN ('collected','transferred','analyzed','stored',"
        "'submitted_court','disposed')",
    )
    op.create_index("idx_custody_evidence", "custody_events", ["evidence_id"])

    # --- append-only trigger (blocks everyone, incl. owner/superuser) --------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evidence_custody_events_no_mutate()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'custody_events is append-only (FR-EVID-03): % is not permitted',
                TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER custody_events_block_update
            BEFORE UPDATE ON custody_events
            FOR EACH ROW EXECUTE FUNCTION evidence_custody_events_no_mutate();
        """
    )
    op.execute(
        """
        CREATE TRIGGER custody_events_block_delete
            BEFORE DELETE ON custody_events
            FOR EACH ROW EXECUTE FUNCTION evidence_custody_events_no_mutate();
        """
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

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON evidence_items TO {APP_ROLE}")

    # custody_events: SELECT + INSERT only. Lock out PUBLIC, then grant the two
    # privileges the app needs, then belt-and-suspenders REVOKE per Section 9.3.3.
    op.execute("REVOKE ALL ON custody_events FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON custody_events TO {APP_ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON custody_events FROM {APP_ROLE}")
    op.execute(
        f"GRANT USAGE, SELECT ON SEQUENCE custody_events_id_seq TO {APP_ROLE}"
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS custody_events_block_update ON custody_events")
    op.execute("DROP TRIGGER IF EXISTS custody_events_block_delete ON custody_events")
    op.execute("DROP FUNCTION IF EXISTS evidence_custody_events_no_mutate()")
    op.drop_table("custody_events")
    op.drop_table("evidence_items")
    # The cluster-global role is intentionally left in place: other evidence_db
    # instances (e.g. the test database) may still depend on it.
