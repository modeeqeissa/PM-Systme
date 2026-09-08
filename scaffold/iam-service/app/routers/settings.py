"""/iam-settings — admin-editable password policy (FR-IAM-07, SRS §8.1).

The `IAM_PASSWORD_*` env vars seed the defaults; a `PATCH` here writes an
`iam_settings` row that overrides one at runtime and takes effect immediately
(the in-process policy cache is reloaded before the response is returned).
Gated on `iam.settings.{read,write}` — iam-service's own admin codes, held by
"ICT Admin".
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.models import IamSetting, User
from app.schemas import IamSettingsOut, IamSettingsPatch
from app.services import audit_events, settings

router = APIRouter(prefix="/iam-settings", tags=["settings"])


def _out() -> IamSettingsOut:
    return IamSettingsOut(values=settings.effective(), overridden=settings.overridden())


@router.get(
    "",
    response_model=IamSettingsOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks iam.settings.read"},
    },
)
async def get_iam_settings(
    _: User = Depends(require_permission("iam.settings.read")),
) -> IamSettingsOut:
    return _out()


@router.patch(
    "",
    response_model=IamSettingsOut,
    responses={
        400: {"description": "Unknown key or invalid value"},
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks iam.settings.write"},
    },
)
async def update_iam_settings(
    payload: IamSettingsPatch,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_permission("iam.settings.write")),
) -> IamSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _out()

    canonical: dict[str, str] = {}
    for key, raw in changes.items():
        try:
            canonical[key] = settings.coerce(key, raw)
        except settings.SettingError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    now = dt.datetime.now(dt.timezone.utc)
    for key, value in canonical.items():
        row = await session.get(IamSetting, key)
        if row is None:
            session.add(IamSetting(key=key, value=value, updated_at=now, updated_by=admin.id))
        else:
            row.value = value
            row.updated_at = now
            row.updated_by = admin.id
    await session.flush()
    await settings.refresh(session)

    audit_events.iam_settings_updated(
        session,
        actor=admin,
        changed=canonical,  # canonical string form of each changed key
        effective=settings.effective(),
    )
    return _out()
