"""officer_user_map + consumed_events + seed notification_templates

officer_user_map and consumed_events are service-local infrastructure (SRS
§9.4 idempotency + the officer_id -> user_id lookup app.models.notification.
OfficerUserMap documents), not SRS §9.3.8 domain tables.

notification_templates.code is the SRS §9.3.8 table's only column — there is
no template-body column, so the rendered message text lives in versioned
application code (app/services/templates.py) rather than an editable DB
field; this migration just seeds the codes so the FK from notifications
.template_code has rows to reference. See TODO.md TD-004.

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

TEMPLATE_CODES = [
    "CERT_EXPIRING",
    "CERT_EXPIRED",
    "TRANSFER_APPROVED",
    "TRANSFER_REJECTED",
    "LEAVE_APPROVED",
    "LEAVE_REJECTED",
    "FOLLOWUP_OVERDUE",
    "ACCOUNT_LOCKED_OUT",
]


def upgrade():
    op.create_table(
        "officer_user_map",
        sa.Column("officer_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
    )

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

    conn = op.get_bind()
    meta = sa.MetaData()
    templates = sa.Table("notification_templates", meta, autoload_with=conn)
    conn.execute(templates.insert(), [{"code": c} for c in TEMPLATE_CODES])


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM notification_templates WHERE code = ANY(:codes)"),
        {"codes": TEMPLATE_CODES},
    )
    op.drop_table("consumed_events")
    op.drop_table("officer_user_map")
