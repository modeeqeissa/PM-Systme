"""Read access to the gateway's own request/response log (FR-INT-05)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.models import ExternalSystemLog
from app.schemas import ExternalSystemLogOut, LogDirection

router = APIRouter(prefix="/external-system-logs", tags=["external-system-logs"])


@router.get(
    "",
    response_model=list[ExternalSystemLogOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks integration.read"}},
)
async def list_external_system_logs(
    system_name: str | None = Query(default=None),
    direction: LogDirection | None = Query(default=None),
    correlation_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("integration.read")),
) -> list[ExternalSystemLogOut]:
    q = select(ExternalSystemLog).order_by(ExternalSystemLog.id.desc())
    if system_name is not None:
        q = q.where(ExternalSystemLog.system_name == system_name)
    if direction is not None:
        q = q.where(ExternalSystemLog.direction == direction.value)
    if correlation_id is not None:
        q = q.where(ExternalSystemLog.correlation_id == correlation_id)
    rows = (await session.scalars(q)).all()
    return [ExternalSystemLogOut.model_validate(r) for r in rows]
