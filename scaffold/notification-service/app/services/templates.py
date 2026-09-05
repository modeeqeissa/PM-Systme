"""Notification message templates.

notification_templates (SRS §9.3.8) has only a `code` column — no template
body — so the rendered text lives here in versioned application code rather
than an admin-editable DB field. The DB table still exists and is seeded
with these same codes (migration 0002) purely so notifications.template_code
has something to reference via its FK; app code is the source of truth for
content, matching how case-service/hr-service treat outbox event *shapes* as
code, not data.
"""

TEMPLATES: dict[str, str] = {
    "CERT_EXPIRING": (
        "Your certification (certification_id={certification_id}) is "
        "expiring soon (expires_date={expires_date})."
    ),
    "CERT_EXPIRED": (
        "Your certification (certification_id={certification_id}) has "
        "expired (expires_date={expires_date})."
    ),
    "TRANSFER_APPROVED": (
        "Your transfer request has been approved, effective {effective_date}."
    ),
    "TRANSFER_REJECTED": "Your transfer request has been rejected.",
    "LEAVE_APPROVED": "Your leave request has been approved.",
    "LEAVE_REJECTED": "Your leave request has been rejected.",
    "FOLLOWUP_OVERDUE": (
        "A community follow-up action assigned to you "
        "(follow_up_action_id={follow_up_action_id}) is now overdue."
    ),
    "ACCOUNT_LOCKED_OUT": (
        "Your account has been locked after repeated failed login attempts. "
        "Contact your station's ICT admin to unlock it."
    ),
}


def render(template_code: str, payload: dict) -> str:
    template = TEMPLATES[template_code]
    return template.format(**payload)
