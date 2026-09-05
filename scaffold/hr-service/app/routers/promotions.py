"""Promotion recording — FR-HR-04.

No approval workflow / status column on promotions (unlike transfers/leave) —
matches docs Section 9.3.6 exactly, so a promotion is recorded as already
decided and immediately updates the officer's rank. effective_date and
approved_by are therefore supplied at recording time rather than by a
separate approve step.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Officer, Promotion
from app.schemas import PromotionCreate, PromotionOut

router = APIRouter(prefix="/officers/{officer_id}/promotions", tags=["promotions"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=PromotionOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.promotion.write"},
        404: {"description": "No officer with that id, or approved_by does not exist"},
    },
)
async def record_promotion(
    officer_id: uuid.UUID,
    payload: PromotionCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.promotion.write")),
) -> PromotionOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    approver = await session.get(Officer, payload.approved_by)
    if approver is None:
        raise HTTPException(status_code=404, detail="approved_by does not exist")

    previous_rank = officer.rank
    promotion = Promotion(
        officer_id=officer_id,
        previous_rank=previous_rank,
        new_rank=payload.new_rank,
        effective_date=payload.effective_date,
        approved_by=payload.approved_by,
    )
    session.add(promotion)
    officer.rank = payload.new_rank
    await session.flush()
    await session.refresh(promotion)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PromotionRecorded",
        aggregate_type="promotion",
        aggregate_id=promotion.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "promotion_id": str(promotion.id),
            "officer_id": str(officer_id),
            "previous_rank": previous_rank,
            "new_rank": payload.new_rank,
            "effective_date": payload.effective_date.isoformat(),
            "approved_by": str(payload.approved_by),
        },
    )
    return PromotionOut.model_validate(promotion)


@router.get(
    "",
    response_model=list[PromotionOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.promotion.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_promotions(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.promotion.read")),
) -> list[PromotionOut]:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(Promotion)
        .where(Promotion.officer_id == officer_id)
        .order_by(Promotion.created_at.desc())
    )
    rows = (await session.scalars(q)).all()
    return [PromotionOut.model_validate(p) for p in rows]
