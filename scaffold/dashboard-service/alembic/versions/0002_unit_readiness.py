"""dimensions feeding mv_unit_readiness (docs Section 9.3.7, FR-DASH-02)

mv_unit_readiness (certified_officer_pct, on_leave_count per unit) is
computed at read time (app/services/unit_readiness.py) from these
incrementally-maintained dimension tables rather than stored as a counter
table: the on-leave component is date-relative (a leave approved today for
next week only "counts" once its start_date arrives), which a per-event
counter can't track without a scheduler. Same rebuild-from-the-log property
as the mv_* tables.

The SRS §9.3.7 named the triggering events "OfficerTransferred" /
"CertificationExpiring"; the services that now exist emit
TransferStatusChanged / OfficerCertificationStatusChanged etc. — mapped in
app/services/projections.py.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06
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
        "dash_unit",
        sa.Column("unit_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("station_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100)),
    )
    op.create_index("idx_dash_unit_station", "dash_unit", ["station_id"])

    op.create_table(
        "dash_officer",
        sa.Column("officer_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("unit_id", pg.UUID(as_uuid=True), nullable=False),
    )
    op.create_index("idx_dash_officer_unit", "dash_officer", ["unit_id"])

    op.create_table(
        "dash_transfer",
        sa.Column("transfer_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("to_unit_id", pg.UUID(as_uuid=True), nullable=False),
    )

    op.create_table(
        "dash_leave",
        sa.Column("leave_request_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("idx_dash_leave_officer", "dash_leave", ["officer_id"])

    op.create_table(
        "dash_officer_cert",
        sa.Column("officer_certification_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("officer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("idx_dash_officer_cert_officer", "dash_officer_cert", ["officer_id"])


def downgrade():
    op.drop_table("dash_officer_cert")
    op.drop_table("dash_leave")
    op.drop_table("dash_transfer")
    op.drop_table("dash_officer")
    op.drop_table("dash_unit")
