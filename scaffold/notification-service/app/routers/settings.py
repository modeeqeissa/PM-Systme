"""/notification-settings — admin-editable retention window (Phase 5).

`NOTIFICATION_RETENTION_DAYS` seeds the default; a `PATCH` here writes a
`notification_settings` row that overrides it at runtime and takes effect on
the retention worker's next pass (the in-process cache is reloaded before the
response is returned). Gated on `notification.settings.{read,write}` — held by
"ICT Admin" (iam migration 0011).

notification_db is not in CLAUDE.md rule 3's audit scope and this service has
no outbox wiring, so — like `PUT /notification-preferences` (TD-006) — a
settings change emits no domain/audit event.
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.models import NotificationSetting
from app.schemas import NotificationSettingsOut, NotificationSettingsPatch
from app.services import settings

router = APIRouter(prefix="/notification-settings", tags=["notification-settings"])


def _out() -> NotificationSettingsOut:
    return NotificationSettingsOut(
        values=settings.effective(), overridden=settings.overridden()
    )


@router.get(
    "",
    response_model=NotificationSettingsOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks notification.settings.read"},
    },
)
async def get_notification_settings(
    _: dict = Depends(require_permission("notification.settings.read")),
) -> NotificationSettingsOut:
    return _out()


@router.patch(
    "",
    response_model=NotificationSettingsOut,
    responses={
        400: {"description": "Unknown key or invalid value"},
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks notification.settings.write"},
    },
)
async def update_notification_settings(
    payload: NotificationSettingsPatch,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("notification.settings.write")),
) -> NotificationSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _out()

    canonical: dict[str, str] = {}
    for key, raw in changes.items():
        try:
            canonical[key] = settings.coerce(key, raw)
        except settings.SettingError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    admin_id = uuid.UUID(claims["sub"])
    now = dt.datetime.now(dt.timezone.utc)
    for key, value in canonical.items():
        row = await session.get(NotificationSetting, key)
        if row is None:
            session.add(
                NotificationSetting(
                    key=key, value=value, updated_at=now, updated_by=admin_id
                )
            )
        else:
            row.value = value
            row.updated_at = now
            row.updated_by = admin_id
    await session.flush()
    await settings.refresh(session)
    return _out()
