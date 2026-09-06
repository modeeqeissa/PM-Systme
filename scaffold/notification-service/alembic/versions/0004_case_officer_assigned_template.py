"""seed the CASE_OFFICER_ASSIGNED notification template (FR-CASE-07)

case-service now emits `CaseOfficerAssigned` when a supporting officer is
assigned to — or re-roled on — a case. notification-service consumes
`case.officer_assigned` and queues a notification for that officer
(app/events/mapping.py); this migration adds the template row its
`template_code` FK points at. Body placeholders are str.format-style against
`notifications.payload` (case_id, officer_id, role_on_case, previous_role).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_CODE = "CASE_OFFICER_ASSIGNED"
_SUBJECT = "Assigned to a case"
_BODY = (
    "You have been assigned to case {case_id} as {role_on_case}."
)


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    templates = sa.Table("notification_templates", meta, autoload_with=conn)
    conn.execute(
        pg.insert(templates)
        .values(code=_CODE, subject=_SUBJECT, body=_BODY)
        .on_conflict_do_update(
            index_elements=["code"], set_={"subject": _SUBJECT, "body": _BODY}
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM notification_templates WHERE code = :c"), {"c": _CODE}
    )
