"""Notification message rendering (FR-NOTIF-01).

Template text lives in the `notification_templates` rows (subject/body,
corrected SRS §9.3.8) — seeded by migration 0003, editable without a deploy.
`render` loads the row and formats `body` (and `subject`, if present)
against `notifications.payload` with str.format placeholders.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationTemplate


class TemplateError(Exception):
    """Unknown template code, or a placeholder the payload doesn't satisfy."""


async def render(
    session: AsyncSession, template_code: str, payload: dict
) -> tuple[str | None, str]:
    row = await session.scalar(
        select(NotificationTemplate).where(NotificationTemplate.code == template_code)
    )
    if row is None:
        raise TemplateError(f"unknown template_code {template_code!r}")
    try:
        body = row.body.format(**payload)
        subject = row.subject.format(**payload) if row.subject else None
    except (KeyError, IndexError) as exc:
        raise TemplateError(
            f"template {template_code!r} placeholder not in payload: {exc}"
        ) from exc
    return subject, body
