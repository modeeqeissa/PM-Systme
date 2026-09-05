"""Stub adapters, one per named external system (FR-INT-01..04, TD-005).

Every call logs an inbound entry (the request PMP received) and an outbound
entry (the fake call this stub "made") sharing one correlation_id, then
returns a response clearly marked `mock: true` — there is nothing real to
integrate with yet. The per-system kill switch (integration_configs.enabled)
is checked first (FR-INT-05: authenticated, scoped, logged — a disabled
system logs nothing and refuses the call outright).
"""
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import ExternalSystemLog, IntegrationConfig
from app.schemas import AdapterCallResponse
from app.services.adapters import ADAPTERS, fake_response

router = APIRouter(prefix="/adapters", tags=["adapters"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "/{system_name}/call",
    response_model=AdapterCallResponse,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks integration.write"},
        404: {"description": "Unknown system_name"},
        409: {"description": "This system's integration is disabled (kill switch)"},
    },
)
async def call_adapter(
    system_name: str,
    request: Request,
    payload: dict = Body(default_factory=dict),
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("integration.write")),
) -> AdapterCallResponse:
    system_name = system_name.upper()
    if system_name not in ADAPTERS:
        raise HTTPException(status_code=404, detail="Unknown system_name")

    config = await session.scalar(
        select(IntegrationConfig).where(IntegrationConfig.system_name == system_name)
    )
    if config is None or not config.enabled:
        raise HTTPException(
            status_code=409, detail="This system's integration is disabled (kill switch)"
        )

    correlation_id_str = request.state.correlation_id
    correlation_id = uuid.UUID(correlation_id_str)
    session.add(
        ExternalSystemLog(
            system_name=system_name, direction="inbound", correlation_id=correlation_id
        )
    )
    body = fake_response(system_name, correlation_id_str, payload)
    session.add(
        ExternalSystemLog(
            system_name=system_name,
            direction="outbound",
            correlation_id=correlation_id,
            response_status=200,
        )
    )

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="ExternalSystemCallLogged",
        aggregate_type="external_system_call",
        aggregate_id=correlation_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "system_name": system_name,
            "correlation_id": correlation_id_str,
            "response_status": 200,
        },
    )
    return AdapterCallResponse.model_validate(body)
