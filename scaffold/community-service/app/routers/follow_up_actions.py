"""Follow-up actions against a concern — FR-COMM-03/04.

docs Section 9.3.4 gives follow_up_actions no free-text description of what
the action actually is — only assigned_to/due_date/status. Flagged rather
than inventing a column the schema doesn't define (CLAUDE.md rule 5).

`status` transitions: pending -> completed is a manual PATCH; pending ->
overdue is set only by the recompute sweep (FR-COMM-04), never accepted
directly from a client — see POST /follow-up-actions/recompute-status.
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Concern, FollowUpAction
from app.schemas import (
    FollowUpActionCreate,
    FollowUpActionOut,
    FollowUpActionStatus,
    FollowUpActionStatusUpdate,
    RecomputeResult,
)
from app.services.overdue import is_overdue

by_concern_router = APIRouter(
    prefix="/concerns/{concern_id}/follow-up-actions", tags=["follow-up-actions"]
)
router = APIRouter(prefix="/follow-up-actions", tags=["follow-up-actions"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_concern_router.post(
    "",
    response_model=FollowUpActionOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No concern with that id"},
    },
)
async def create_follow_up_action(
    concern_id: uuid.UUID,
    payload: FollowUpActionCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> FollowUpActionOut:
    concern = await session.get(Concern, concern_id)
    if concern is None:
        raise HTTPException(status_code=404, detail="No concern with that id")

    action = FollowUpAction(
        concern_id=concern_id, assigned_to=payload.assigned_to, due_date=payload.due_date
    )
    session.add(action)
    await session.flush()
    await session.refresh(action)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="FollowUpActionCreated",
        aggregate_type="follow_up_action",
        aggregate_id=action.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "follow_up_action_id": str(action.id),
            "concern_id": str(concern_id),
            "assigned_to": str(action.assigned_to),
            "due_date": action.due_date.isoformat(),
        },
    )
    return FollowUpActionOut.model_validate(action)


@by_concern_router.get(
    "",
    response_model=list[FollowUpActionOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No concern with that id"},
    },
)
async def list_follow_up_actions_for_concern(
    concern_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[FollowUpActionOut]:
    concern = await session.get(Concern, concern_id)
    if concern is None:
        raise HTTPException(status_code=404, detail="No concern with that id")

    q = (
        select(FollowUpAction)
        .where(FollowUpAction.concern_id == concern_id)
        .order_by(FollowUpAction.due_date)
    )
    rows = (await session.scalars(q)).all()
    return [FollowUpActionOut.model_validate(a) for a in rows]


@router.get(
    "",
    response_model=list[FollowUpActionOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks community.read"}},
)
async def list_follow_up_actions(
    assigned_to: uuid.UUID | None = Query(default=None),
    status_: FollowUpActionStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[FollowUpActionOut]:
    q = select(FollowUpAction).order_by(FollowUpAction.due_date)
    if assigned_to is not None:
        q = q.where(FollowUpAction.assigned_to == assigned_to)
    if status_ is not None:
        q = q.where(FollowUpAction.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [FollowUpActionOut.model_validate(a) for a in rows]


@router.get(
    "/{follow_up_action_id}",
    response_model=FollowUpActionOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No follow-up action with that id"},
    },
)
async def get_follow_up_action(
    follow_up_action_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> FollowUpActionOut:
    action = await session.get(FollowUpAction, follow_up_action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="No follow-up action with that id")
    return FollowUpActionOut.model_validate(action)


@router.patch(
    "/{follow_up_action_id}",
    response_model=FollowUpActionOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No follow-up action with that id"},
        422: {"description": "status 'overdue' is set automatically, not via this endpoint"},
    },
)
async def update_follow_up_action_status(
    follow_up_action_id: uuid.UUID,
    payload: FollowUpActionStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> FollowUpActionOut:
    if payload.status == FollowUpActionStatus.overdue:
        raise HTTPException(
            status_code=422,
            detail="status 'overdue' is set automatically by the recompute sweep, "
            "not via this endpoint",
        )
    action = await session.get(FollowUpAction, follow_up_action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="No follow-up action with that id")

    from_status = action.status
    action.status = payload.status.value
    await session.flush()
    await session.refresh(action)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="FollowUpActionStatusChanged",
        aggregate_type="follow_up_action",
        aggregate_id=action.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "follow_up_action_id": str(action.id),
            "assigned_to": str(action.assigned_to),
            "from_status": from_status,
            "to_status": action.status,
        },
    )
    return FollowUpActionOut.model_validate(action)


@router.post(
    "/recompute-status",
    response_model=RecomputeResult,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
    },
)
async def recompute_follow_up_action_statuses(
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> RecomputeResult:
    """On-demand sweep (FR-COMM-04): flag every pending follow-up action past
    its due_date as overdue. The same recompute also runs in the background
    (app.services.recompute_task, COMMUNITY_RECOMPUTE_ENABLED)."""
    today = dt.date.today()
    actor_id, actor_role = _actor(claims)

    rows = (
        await session.scalars(select(FollowUpAction).where(FollowUpAction.status == "pending"))
    ).all()
    updated = 0
    for row in rows:
        if is_overdue(row.due_date, today=today):
            row.status = "overdue"
            enqueue(
                session,
                event_type="FollowUpActionStatusChanged",
                aggregate_type="follow_up_action",
                aggregate_id=row.id,
                actor_id=actor_id,
                actor_role=actor_role,
                payload={
                    "follow_up_action_id": str(row.id),
                    "assigned_to": str(row.assigned_to),
                    "from_status": "pending",
                    "to_status": "overdue",
                },
            )
            updated += 1

    return RecomputeResult(checked=len(rows), updated=updated)
