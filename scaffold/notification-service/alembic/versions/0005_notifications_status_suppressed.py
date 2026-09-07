"""add 'suppressed' to notifications.status (corrected SRS §9.3.8)

FR-NOTIF-02: when a (recipient, channel) preference is disabled the delivery
worker skips the send. Until now that row landed as 'failed', which was
indistinguishable from a real provider failure. This extends the §9.3.8
status enum with a distinct terminal value:

    'suppressed' — intentionally not delivered (recipient disabled the channel)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-07
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_OLD = "status IN ('queued','sent','delivered','failed')"
_NEW = "status IN ('queued','sent','delivered','failed','suppressed')"


def upgrade():
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_status", "notifications", _NEW)


def downgrade():
    # Fold any suppressed rows back to 'failed' so the tighter constraint holds.
    op.execute("UPDATE notifications SET status = 'failed' WHERE status = 'suppressed'")
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_status", "notifications", _OLD)
