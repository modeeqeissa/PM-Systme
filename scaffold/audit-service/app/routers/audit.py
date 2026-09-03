"""GET /audit and GET /audit/verify — read-only oversight access (FR-AUD-02/03)."""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.models import AuditLog
from app.schemas import AuditEntry, ChainVerification
from app.services.hashchain import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "",
    response_model=list[AuditEntry],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks audit.read"},
    },
)
async def query_audit_log(
    actor_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    service_name: str | None = Query(default=None),
    from_: dt.datetime | None = Query(default=None, alias="from"),
    to: dt.datetime | None = Query(default=None),
    limit: int = Query(default=100, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("audit.read")),
) -> list[AuditEntry]:
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if actor_id is not None:
        q = q.where(AuditLog.actor_id == actor_id)
    if entity_type is not None:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(AuditLog.entity_id == entity_id)
    if action is not None:
        q = q.where(AuditLog.action == action)
    if service_name is not None:
        q = q.where(AuditLog.service_name == service_name)
    if from_ is not None:
        q = q.where(AuditLog.timestamp >= from_)
    if to is not None:
        q = q.where(AuditLog.timestamp <= to)
    q = q.limit(limit).offset(offset)

    rows = (await session.scalars(q)).all()
    return [AuditEntry.from_model(r) for r in rows]


@router.get(
    "/verify",
    response_model=ChainVerification,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks audit.read"},
    },
)
async def verify_audit_chain(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("audit.read")),
) -> ChainVerification:
    checked, valid, broken_at = await verify_chain(session)
    return ChainVerification(entries_checked=checked, valid=valid, broken_at=broken_at)
