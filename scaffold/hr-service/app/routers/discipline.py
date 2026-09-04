"""Discipline records — FR-HR-06.

Gated end to end on hr.discipline.read / hr.discipline.write, which docs
Section 2.3 names as HR/command-only (no other permission unlocks these
routes — case.approve, hr.transfer.approve etc. all get a plain 403 here).
No Commissioner/Command Staff role is seeded yet (out of scope for this
build), so today only the "HR Officer" role can reach discipline data at
all — flagged, not silently widened.

Every mutating action here is exactly the kind of sensitive event
FR-AUD-01/SRS §5.8 cares about most, so create/update/delete all enqueue to
the outbox like everything else in this service.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import DisciplineRecord, Officer
from app.schemas import DisciplineRecordCreate, DisciplineRecordOut, DisciplineRecordUpdate

by_officer_router = APIRouter(
    prefix="/officers/{officer_id}/discipline-records", tags=["discipline"]
)
router = APIRouter(prefix="/discipline-records", tags=["discipline"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_officer_router.post(
    "",
    response_model=DisciplineRecordOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.discipline.write"},
        404: {"description": "No officer with that id"},
    },
)
async def create_discipline_record(
    officer_id: uuid.UUID,
    payload: DisciplineRecordCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.discipline.write")),
) -> DisciplineRecordOut:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    record = DisciplineRecord(
        officer_id=officer_id, confidentiality_level=payload.confidentiality_level
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="DisciplineRecordCreated",
        aggregate_type="discipline_record",
        aggregate_id=record.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "discipline_record_id": str(record.id),
            "officer_id": str(officer_id),
            "confidentiality_level": record.confidentiality_level,
        },
    )
    return DisciplineRecordOut.model_validate(record)


@by_officer_router.get(
    "",
    response_model=list[DisciplineRecordOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.discipline.read"},
        404: {"description": "No officer with that id"},
    },
)
async def list_officer_discipline_records(
    officer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.discipline.read")),
) -> list[DisciplineRecordOut]:
    officer = await session.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status_code=404, detail="No officer with that id")

    q = (
        select(DisciplineRecord)
        .where(DisciplineRecord.officer_id == officer_id)
        .order_by(DisciplineRecord.created_at.desc())
    )
    rows = (await session.scalars(q)).all()
    return [DisciplineRecordOut.model_validate(r) for r in rows]


@router.get(
    "/{discipline_record_id}",
    response_model=DisciplineRecordOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.discipline.read"},
        404: {"description": "No discipline record with that id"},
    },
)
async def get_discipline_record(
    discipline_record_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("hr.discipline.read")),
) -> DisciplineRecordOut:
    record = await session.get(DisciplineRecord, discipline_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No discipline record with that id")
    return DisciplineRecordOut.model_validate(record)


@router.patch(
    "/{discipline_record_id}",
    response_model=DisciplineRecordOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.discipline.write"},
        404: {"description": "No discipline record with that id"},
    },
)
async def update_discipline_record(
    discipline_record_id: uuid.UUID,
    payload: DisciplineRecordUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.discipline.write")),
) -> DisciplineRecordOut:
    record = await session.get(DisciplineRecord, discipline_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No discipline record with that id")

    if payload.confidentiality_level is not None:
        record.confidentiality_level = payload.confidentiality_level
    await session.flush()
    await session.refresh(record)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="DisciplineRecordUpdated",
        aggregate_type="discipline_record",
        aggregate_id=record.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "discipline_record_id": str(record.id),
            "officer_id": str(record.officer_id),
            "confidentiality_level": record.confidentiality_level,
        },
    )
    return DisciplineRecordOut.model_validate(record)


@router.delete(
    "/{discipline_record_id}",
    status_code=204,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks hr.discipline.write"},
        404: {"description": "No discipline record with that id"},
    },
)
async def delete_discipline_record(
    discipline_record_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("hr.discipline.write")),
) -> None:
    record = await session.get(DisciplineRecord, discipline_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No discipline record with that id")

    officer_id = record.officer_id
    await session.delete(record)
    await session.flush()

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="DisciplineRecordDeleted",
        aggregate_type="discipline_record",
        aggregate_id=discipline_record_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "discipline_record_id": str(discipline_record_id),
            "officer_id": str(officer_id),
        },
    )
