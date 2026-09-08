"""Officer awards / commendations — docs §9.3.6 revised.

The positive counterpart to discipline_records. Gated on `hr.award.{read,
write}` (iam migration 0010). Unlike discipline records, awards carry no
confidentiality level and no special read-audit — a commendation is a matter
of record, not a restricted file.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Award, Officer
from app.schemas import AwardCreate, AwardOut

by_officer_router = APIRouter(prefix="/officers/{officer_id}/awards", tags=["awards"])
router = APIRouter(prefix="/awards", tags=["awards"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_officer_router.post(
    "",
    response_model=AwardOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.award.write"},
        404: {"description": "No officer with that id, or awarded_by does not exist"},
    },
)
async def record_award(
    officer_id: uuid.UUID,
    payload: AwardCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.award.write")),
) -> AwardOut:
    if await session.get(Officer, officer_id) is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    if payload.awarded_by is not None and await session.get(Officer, payload.awarded_by) is None:
        raise HTTPException(status_code=404, detail="awarded_by does not exist")

    award = Award(
        officer_id=officer_id,
        title=payload.title,
        description=payload.description,
        awarded_date=payload.awarded_date,
        awarded_by=payload.awarded_by,
    )
    session.add(award)
    await session.flush()
    await session.refresh(award)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="AwardRecorded",
        aggregate_type="award",
        aggregate_id=award.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "award_id": str(award.id),
            "officer_id": str(officer_id),
            "title": award.title,
            "awarded_date": award.awarded_date.isoformat(),
            "awarded_by": str(award.awarded_by) if award.awarded_by else None,
        },
    )
    return AwardOut.model_validate(award)


@by_officer_router.get(
    "",
    response_model=list[AwardOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.award.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_officer_awards(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.award.read")),
) -> list[AwardOut]:
    if await session.get(Officer, officer_id) is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    rows = (
        await session.scalars(
            select(Award)
            .where(Award.officer_id == officer_id)
            .order_by(Award.awarded_date.desc())
        )
    ).all()
    return [AwardOut.model_validate(a) for a in rows]


@router.get(
    "/{award_id}",
    response_model=AwardOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.award.read"},
        404: {"description": "No award with that id"},
    },
)
async def get_award(
    award_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.award.read")),
) -> AwardOut:
    award = await session.get(Award, award_id)
    if award is None:
        raise HTTPException(status_code=404, detail="No award with that id")
    return AwardOut.model_validate(award)
