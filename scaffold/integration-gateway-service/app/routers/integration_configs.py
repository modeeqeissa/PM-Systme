"""Per-system kill switch (docs Section 9.3.9). Managed by ICT Admin
(docs Section 2.3: "Manages ... integrations").
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import IntegrationConfig
from app.schemas import IntegrationConfigOut, IntegrationConfigUpdate

router = APIRouter(prefix="/integration-configs", tags=["integration-configs"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.get(
    "",
    response_model=list[IntegrationConfigOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks integration.read"}},
)
async def list_integration_configs(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("integration.read")),
) -> list[IntegrationConfigOut]:
    rows = (
        await session.scalars(select(IntegrationConfig).order_by(IntegrationConfig.system_name))
    ).all()
    return [IntegrationConfigOut.model_validate(c) for c in rows]


@router.get(
    "/{config_id}",
    response_model=IntegrationConfigOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks integration.read"},
        404: {"description": "No integration config with that id"},
    },
)
async def get_integration_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("integration.read")),
) -> IntegrationConfigOut:
    config = await session.get(IntegrationConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No integration config with that id")
    return IntegrationConfigOut.model_validate(config)


@router.patch(
    "/{config_id}",
    response_model=IntegrationConfigOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks integration.write"},
        404: {"description": "No integration config with that id"},
    },
)
async def update_integration_config(
    config_id: int,
    payload: IntegrationConfigUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("integration.write")),
) -> IntegrationConfigOut:
    config = await session.get(IntegrationConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No integration config with that id")

    config.enabled = payload.enabled
    await session.flush()
    await session.refresh(config)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="IntegrationConfigUpdated",
        aggregate_type="integration_config",
        aggregate_id=config.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "integration_config_id": config.id,
            "system_name": config.system_name,
            "enabled": config.enabled,
        },
    )
    return IntegrationConfigOut.model_validate(config)
