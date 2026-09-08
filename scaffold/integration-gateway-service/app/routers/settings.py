"""/integration-settings — admin-editable external-system-log retention (Phase 5).

`INTEGRATION_GATEWAY_LOG_RETENTION_DAYS` seeds the default; a `PATCH` here
writes an `integration_settings` row that overrides it at runtime and takes
effect on the retention worker's next pass (the in-process cache is reloaded
immediately). Gated on `integration.settings.{read,write}` — held by
"ICT Admin" (iam migration 0011).

Every mutating endpoint in this service enqueues a domain event (FR-INT-05 /
CLAUDE.md rule 3); a settings change publishes `IntegrationSettingsUpdated`,
which audit-service records as `integration_settings`/`update`.
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import IntegrationSetting
from app.schemas import IntegrationSettingsOut, IntegrationSettingsPatch
from app.services import settings

router = APIRouter(prefix="/integration-settings", tags=["integration-settings"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


def _out() -> IntegrationSettingsOut:
    return IntegrationSettingsOut(
        values=settings.effective(), overridden=settings.overridden()
    )


@router.get(
    "",
    response_model=IntegrationSettingsOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks integration.settings.read"},
    },
)
async def get_integration_settings(
    _: dict = Depends(require_permission("integration.settings.read")),
) -> IntegrationSettingsOut:
    return _out()


@router.patch(
    "",
    response_model=IntegrationSettingsOut,
    responses={
        400: {"description": "Unknown key or invalid value"},
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks integration.settings.write"},
    },
)
async def update_integration_settings(
    payload: IntegrationSettingsPatch,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("integration.settings.write")),
) -> IntegrationSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _out()

    canonical: dict[str, str] = {}
    for key, raw in changes.items():
        try:
            canonical[key] = settings.coerce(key, raw)
        except settings.SettingError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    actor_id, actor_role = _actor(claims)
    now = dt.datetime.now(dt.timezone.utc)
    for key, value in canonical.items():
        row = await session.get(IntegrationSetting, key)
        admin_uuid = uuid.UUID(actor_id) if actor_id else None
        if row is None:
            session.add(
                IntegrationSetting(
                    key=key, value=value, updated_at=now, updated_by=admin_uuid
                )
            )
        else:
            row.value = value
            row.updated_at = now
            row.updated_by = admin_uuid
    await session.flush()
    await settings.refresh(session)

    enqueue(
        session,
        event_type="IntegrationSettingsUpdated",
        aggregate_type="integration_settings",
        aggregate_id=actor_id,  # keyless config table — key on the acting admin
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "actor_id": actor_id,
            "changed": canonical,
            "effective": {k: str(v) for k, v in settings.effective().items()},
        },
    )
    return _out()
