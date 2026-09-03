"""initial case_db schema — mirrors docs Section 9.3.2 exactly

Revision ID: 0001
Revises:
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')  # for gen_random_uuid()

    op.create_table(
        "incidents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("reported_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("station_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_sync_id", pg.UUID(as_uuid=True), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_incidents_station", "incidents", ["station_id"])

    op.create_table(
        "cases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_number", sa.String(30), nullable=False, unique=True),
        sa.Column("incident_id", pg.UUID(as_uuid=True), sa.ForeignKey("incidents.id")),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="open",
        ),
        sa.Column("lead_officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        "ck_cases_status",
        "cases",
        "status IN ('open','investigating','referred_prosecution','closed','suspended')",
    )
    op.create_index("idx_cases_status", "cases", ["status"])
    op.create_index("idx_cases_lead_officer", "cases", ["lead_officer_id"])

    op.create_table(
        "case_officers",
        sa.Column("case_id", pg.UUID(as_uuid=True), sa.ForeignKey("cases.id"), primary_key=True),
        sa.Column("officer_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_on_case", sa.String(30), nullable=False),
    )

    op.create_table(
        "arrests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", pg.UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("suspect_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("arrest_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.Text),
        sa.Column("legal_basis", sa.Text),
    )
    op.create_index("idx_arrests_case", "arrests", ["case_id"])

    op.create_table(
        "statements",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", pg.UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("party_type", sa.String(20), nullable=False),
        sa.Column("statement_text", sa.Text, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "ck_statements_party_type", "statements", "party_type IN ('witness','suspect','victim')"
    )

    op.create_table(
        "court_proceedings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_id", pg.UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("hearing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("court_name", sa.String(150)),
        sa.Column("verdict", sa.String(50)),
        sa.Column("notes", sa.Text),
    )


def downgrade():
    op.drop_table("court_proceedings")
    op.drop_table("statements")
    op.drop_table("arrests")
    op.drop_table("case_officers")
    op.drop_table("cases")
    op.drop_table("incidents")
