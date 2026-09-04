"""Performance reviews — FR-HR-07 (Should-have)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Officer, PerformanceReview
from app.schemas import (
    PerformanceReviewCreate,
    PerformanceReviewOut,
    PerformanceReviewUpdate,
)

by_officer_router = APIRouter(
    prefix="/officers/{officer_id}/performance-reviews", tags=["performance"]
)
router = APIRouter(prefix="/performance-reviews", tags=["performance"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_officer_router.post(
    "",
    response_model=PerformanceReviewOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.performance.write"},
        404: {"description": "No officer with that id, or reviewer_id does not exist"},
    },
)
async def create_performance_review(
    officer_id: uuid.UUID,
    payload: PerformanceReviewCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.performance.write")),
) -> PerformanceReviewOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    reviewer = await session.get(Officer, payload.reviewer_id)
    if reviewer is None:
        raise HTTPException(status_code=404, detail="reviewer_id does not exist")

    review = PerformanceReview(
        officer_id=officer_id,
        reviewer_id=payload.reviewer_id,
        period=payload.period,
        score=payload.score,
    )
    session.add(review)
    await session.flush()
    await session.refresh(review)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PerformanceReviewRecorded",
        aggregate_type="performance_review",
        aggregate_id=review.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "performance_review_id": str(review.id),
            "officer_id": str(officer_id),
            "reviewer_id": str(payload.reviewer_id),
            "period": review.period,
            "score": str(review.score),
        },
    )
    return PerformanceReviewOut.model_validate(review)


@by_officer_router.get(
    "",
    response_model=list[PerformanceReviewOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.performance.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_officer_performance_reviews(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.performance.read")),
) -> list[PerformanceReviewOut]:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(PerformanceReview)
        .where(PerformanceReview.officer_id == officer_id)
        .order_by(PerformanceReview.created_at.desc())
    )
    rows = (await session.scalars(q)).all()
    return [PerformanceReviewOut.model_validate(r) for r in rows]


@router.get(
    "/{performance_review_id}",
    response_model=PerformanceReviewOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.performance.read"},
        404: {"description": "No performance review with that id"},
    },
)
async def get_performance_review(
    performance_review_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.performance.read")),
) -> PerformanceReviewOut:
    review = await session.get(PerformanceReview, performance_review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No performance review with that id")
    return PerformanceReviewOut.model_validate(review)


@router.patch(
    "/{performance_review_id}",
    response_model=PerformanceReviewOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.performance.write"},
        404: {"description": "No performance review with that id"},
    },
)
async def update_performance_review(
    performance_review_id: uuid.UUID,
    payload: PerformanceReviewUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.performance.write")),
) -> PerformanceReviewOut:
    review = await session.get(PerformanceReview, performance_review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No performance review with that id")

    if payload.period is not None:
        review.period = payload.period
    if payload.score is not None:
        review.score = payload.score
    await session.flush()
    await session.refresh(review)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PerformanceReviewUpdated",
        aggregate_type="performance_review",
        aggregate_id=review.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "performance_review_id": str(review.id),
            "officer_id": str(review.officer_id),
            "period": review.period,
            "score": str(review.score),
        },
    )
    return PerformanceReviewOut.model_validate(review)


@router.delete(
    "/{performance_review_id}",
    status_code=204,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.performance.write"},
        404: {"description": "No performance review with that id"},
    },
)
async def delete_performance_review(
    performance_review_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.performance.write")),
) -> None:
    review = await session.get(PerformanceReview, performance_review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No performance review with that id")

    officer_id = review.officer_id
    await session.delete(review)
    await session.flush()

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PerformanceReviewDeleted",
        aggregate_type="performance_review",
        aggregate_id=performance_review_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "performance_review_id": str(performance_review_id),
            "officer_id": str(officer_id),
        },
    )
