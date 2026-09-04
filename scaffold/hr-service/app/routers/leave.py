"""Leave requests + approval workflow — FR-HR-05. Same shape as transfers.py."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import LeaveRequest, Officer
from app.schemas import LeaveRequestCreate, LeaveRequestOut, LeaveStatusUpdate, WorkflowStatus

by_officer_router = APIRouter(
    prefix="/officers/{officer_id}/leave-requests", tags=["leave"]
)
router = APIRouter(prefix="/leave-requests", tags=["leave"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_officer_router.post(
    "",
    response_model=LeaveRequestOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.leave.write"},
        404: {"description": "No officer with that id"},
    },
)
async def request_leave(
    officer_id: uuid.UUID,
    payload: LeaveRequestCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.leave.write")),
) -> LeaveRequestOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    leave = LeaveRequest(officer_id=officer_id, leave_type=payload.leave_type, status="pending")
    session.add(leave)
    await session.flush()
    await session.refresh(leave)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="LeaveRequested",
        aggregate_type="leave_request",
        aggregate_id=leave.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "leave_request_id": str(leave.id),
            "officer_id": str(officer_id),
            "leave_type": leave.leave_type,
        },
    )
    return LeaveRequestOut.model_validate(leave)


@by_officer_router.get(
    "",
    response_model=list[LeaveRequestOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.leave.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_officer_leave_requests(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.leave.read")),
) -> list[LeaveRequestOut]:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(LeaveRequest)
        .where(LeaveRequest.officer_id == officer_id)
        .order_by(LeaveRequest.created_at.desc())
    )
    rows = (await session.scalars(q)).all()
    return [LeaveRequestOut.model_validate(lr) for lr in rows]


@router.get(
    "",
    response_model=list[LeaveRequestOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.leave.read"},
    },
)
async def list_leave_requests(
    status_: WorkflowStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.leave.read")),
) -> list[LeaveRequestOut]:
    """Approver queue — every leave request, optionally filtered by status."""
    q = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if status_ is not None:
        q = q.where(LeaveRequest.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [LeaveRequestOut.model_validate(lr) for lr in rows]


@router.patch(
    "/{leave_request_id}",
    response_model=LeaveRequestOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.leave.approve"},
        404: {"description": "No leave request with that id"},
        409: {"description": "Leave request is not pending"},
    },
)
async def decide_leave_request(
    leave_request_id: uuid.UUID,
    payload: LeaveStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.leave.approve")),
) -> LeaveRequestOut:
    leave = await session.get(LeaveRequest, leave_request_id)
    if leave is None:
        raise HTTPException(status_code=404, detail="No leave request with that id")
    if leave.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Leave request is {leave.status}, not pending"
        )

    from_status = leave.status
    leave.status = payload.status.value
    await session.flush()
    await session.refresh(leave)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="LeaveStatusChanged",
        aggregate_type="leave_request",
        aggregate_id=leave.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "leave_request_id": str(leave.id),
            "officer_id": str(leave.officer_id),
            "from_status": from_status,
            "to_status": leave.status,
        },
    )
    return LeaveRequestOut.model_validate(leave)
