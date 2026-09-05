"""template subject/body + notification_preferences + supervisor map

Corrected SRS §9.3.8:
* notification_templates gains subject (VARCHAR(200) NULLABLE) and body
  (TEXT NOT NULL) — template text moves out of app code into these rows so
  it can be edited without a deploy (TD-004's "flagged, not invented" note
  is now closed).
* new table notification_preferences (FR-NOTIF-02) — per-user opt-out per
  channel.

Also: officer_user_map gains supervisor_officer_id, fed by hr-service's new
OfficerCreated (supervisor_id) / OfficerSupervisorChanged events, so the
FR-COMM-04 "notify the assignee's supervisor" path can resolve the
supervisor's recipient user_id without touching hr_db (CLAUDE.md rule 1).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# code -> (subject, body). Body placeholders are str.format-style against
# notifications.payload.
_TEMPLATES = {
    "CERT_EXPIRING": (
        "Certification expiring soon",
        "Your certification (certification_id={certification_id}) is expiring "
        "soon (expires_date={expires_date}).",
    ),
    "CERT_EXPIRED": (
        "Certification expired",
        "Your certification (certification_id={certification_id}) has expired "
        "(expires_date={expires_date}).",
    ),
    "TRANSFER_APPROVED": (
        "Transfer approved",
        "Your transfer request has been approved, effective {effective_date}.",
    ),
    "TRANSFER_REJECTED": (
        "Transfer rejected",
        "Your transfer request has been rejected.",
    ),
    "LEAVE_APPROVED": ("Leave approved", "Your leave request has been approved."),
    "LEAVE_REJECTED": ("Leave rejected", "Your leave request has been rejected."),
    "FOLLOWUP_OVERDUE": (
        "Follow-up action overdue",
        "A community follow-up action assigned to you "
        "(follow_up_action_id={follow_up_action_id}) is now overdue.",
    ),
    "FOLLOWUP_OVERDUE_SUPERVISOR": (
        "Follow-up action overdue (officer you supervise)",
        "A community follow-up action (follow_up_action_id={follow_up_action_id}) "
        "assigned to an officer you supervise is now overdue.",
    ),
    "ACCOUNT_LOCKED_OUT": (
        "Account locked",
        "Your account has been locked after repeated failed login attempts. "
        "Contact your station's ICT admin to unlock it.",
    ),
}


def upgrade():
    op.add_column(
        "notification_templates", sa.Column("subject", sa.String(200), nullable=True)
    )
    op.add_column(
        "notification_templates",
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("notification_templates", "body", server_default=None)

    conn = op.get_bind()
    meta = sa.MetaData()
    templates = sa.Table("notification_templates", meta, autoload_with=conn)
    for code, (subject, body) in _TEMPLATES.items():
        # FOLLOWUP_OVERDUE_SUPERVISOR is brand new; the rest already exist.
        conn.execute(
            pg.insert(templates)
            .values(code=code, subject=subject, body=body)
            .on_conflict_do_update(
                index_elements=["code"], set_={"subject": subject, "body": body}
            )
        )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("user_id", "channel", name="uq_notification_preferences_user_channel"),
    )
    op.create_check_constraint(
        "ck_notification_preferences_channel",
        "notification_preferences",
        "channel IN ('email','sms','push','in_app')",
    )

    op.add_column(
        "officer_user_map",
        sa.Column("supervisor_officer_id", pg.UUID(as_uuid=True), nullable=True),
    )


def downgrade():
    op.drop_column("officer_user_map", "supervisor_officer_id")
    op.drop_table("notification_preferences")
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM notification_templates WHERE code = 'FOLLOWUP_OVERDUE_SUPERVISOR'")
    )
    op.drop_column("notification_templates", "body")
    op.drop_column("notification_templates", "subject")
