"""Transfer requests + approval workflow — FR-HR-03.

Two routers share this module: one nested under an officer (request +
history), one top-level (the approver's queue + the approve/reject action,
found by transfer id rather than officer id).
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Officer, Transfer, Unit
from app.schemas import (
    ApprovalStatus,
    TransferCreate,
    TransferOut,
    TransferStatusUpdate,
    WorkflowStatus,
)
from app.services.assignments import reassign

by_officer_router = APIRouter(prefix="/officers/{officer_id}/transfers", tags=["transfers"])
router = APIRouter(prefix="/transfers", tags=["transfers"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_officer_router.post(
    "",
    response_model=TransferOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.transfer.write"},
        404: {"description": "No officer with that id, or to_unit_id does not exist"},
    },
)
async def request_transfer(
    officer_id: uuid.UUID,
    payload: TransferCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.transfer.write")),
) -> TransferOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")
    to_unit = await session.get(Unit, payload.to_unit_id)
    if to_unit is None:
        raise HTTPException(status_code=404, detail="to_unit_id does not exist")

    transfer = Transfer(
        officer_id=officer_id,
        from_unit_id=officer.unit_id,
        to_unit_id=payload.to_unit_id,
        status="pending",
    )
    session.add(transfer)
    await session.flush()
    await session.refresh(transfer)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="TransferRequested",
        aggregate_type="transfer",
        aggregate_id=transfer.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "transfer_id": str(transfer.id),
            "officer_id": str(officer_id),
            "from_unit_id": str(transfer.from_unit_id) if transfer.from_unit_id else None,
            "to_unit_id": str(transfer.to_unit_id) if transfer.to_unit_id else None,
        },
    )
    return TransferOut.model_validate(transfer)


@by_officer_router.get(
    "",
    response_model=list[TransferOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.transfer.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_officer_transfers(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.transfer.read")),
) -> list[TransferOut]:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(Transfer)
        .where(Transfer.officer_id == officer_id)
        .order_by(Transfer.created_at.desc())
    )
    rows = (await session.scalars(q)).all()
    return [TransferOut.model_validate(t) for t in rows]


@router.get(
    "",
    response_model=list[TransferOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.transfer.read"},
    },
)
async def list_transfers(
    status_: WorkflowStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.transfer.read")),
) -> list[TransferOut]:
    """Approver queue — every transfer request, optionally filtered by status."""
    q = select(Transfer).order_by(Transfer.created_at.desc())
    if status_ is not None:
        q = q.where(Transfer.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [TransferOut.model_validate(t) for t in rows]


@router.patch(
    "/{transfer_id}",
    response_model=TransferOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.transfer.approve"},
        404: {"description": "No transfer with that id"},
        409: {"description": "Transfer is not pending"},
    },
)
async def decide_transfer(
    transfer_id: uuid.UUID,
    payload: TransferStatusUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.transfer.approve")),
) -> TransferOut:
    transfer = await session.get(Transfer, transfer_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail="No transfer with that id")
    if transfer.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Transfer is {transfer.status}, not pending"
        )

    from_status = transfer.status
    transfer.status = payload.status.value

    if payload.status == ApprovalStatus.approved and transfer.to_unit_id is not None:
        officer = await session.get(Officer, transfer.officer_id)
        await reassign(
            session,
            officer,
            unit_id=transfer.to_unit_id,
            start_date=dt.date.today(),
        )

    await session.flush()
    await session.refresh(transfer)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="TransferStatusChanged",
        aggregate_type="transfer",
        aggregate_id=transfer.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "transfer_id": str(transfer.id),
            "officer_id": str(transfer.officer_id),
            "from_status": from_status,
            "to_status": transfer.status,
        },
    )
    return TransferOut.model_validate(transfer)
