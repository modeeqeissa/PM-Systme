"""Organisational units — a lightweight lookup table officers/assignments/
transfers reference; not itself a functional requirement, but required
infrastructure for FR-HR-01/02/03 to be usable end to end.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Unit
from app.schemas import UnitCreate, UnitOut

router = APIRouter(prefix="/units", tags=["units"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=UnitOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.unit.write"},
    },
)
async def create_unit(
    payload: UnitCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.unit.write")),
) -> UnitOut:
    unit = Unit(name=payload.name, station_id=payload.station_id)
    session.add(unit)
    await session.flush()
    await session.refresh(unit)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="UnitCreated",
        aggregate_type="unit",
        aggregate_id=unit.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"unit_id": str(unit.id), "name": unit.name, "station_id": str(unit.station_id)},
    )
    return UnitOut.model_validate(unit)


@router.get(
    "",
    response_model=list[UnitOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.unit.read"},
    },
)
async def list_units(
    station_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.unit.read")),
) -> list[UnitOut]:
    q = select(Unit).order_by(Unit.name)
    if station_id is not None:
        q = q.where(Unit.station_id == station_id)
    rows = (await session.scalars(q)).all()
    return [UnitOut.model_validate(u) for u in rows]
