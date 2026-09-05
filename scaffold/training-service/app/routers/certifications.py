"""Certification types — each tied to the course that earns it (FR-TRAIN-01).

A Certification is the issuable qualification record referenced by
OfficerCertification when it's actually granted to an officer; its own display
name is the linked course's title (docs Section 9.3.5 gives it no name column
of its own).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Certification, Course
from app.schemas import CertificationCreate, CertificationOut

router = APIRouter(prefix="/certifications", tags=["certifications"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=CertificationOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "course_id does not exist"},
    },
)
async def create_certification(
    payload: CertificationCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> CertificationOut:
    course = await session.get(Course, payload.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="course_id does not exist")

    cert = Certification(course_id=payload.course_id)
    session.add(cert)
    await session.flush()
    await session.refresh(cert)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CertificationCreated",
        aggregate_type="certification",
        aggregate_id=cert.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"certification_id": cert.id, "course_id": cert.course_id},
    )
    return CertificationOut.model_validate(cert)


@router.get(
    "",
    response_model=list[CertificationOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks training.cert.read"}},
)
async def list_certifications(
    course_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[CertificationOut]:
    q = select(Certification).order_by(Certification.id)
    if course_id is not None:
        q = q.where(Certification.course_id == course_id)
    rows = (await session.scalars(q)).all()
    return [CertificationOut.model_validate(c) for c in rows]


@router.get(
    "/{certification_id}",
    response_model=CertificationOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No certification with that id"},
    },
)
async def get_certification(
    certification_id: int,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> CertificationOut:
    cert = await session.get(Certification, certification_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="No certification with that id")
    return CertificationOut.model_validate(cert)


@router.delete(
    "/{certification_id}",
    status_code=204,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No certification with that id"},
        409: {"description": "Certification still has officer_certifications referencing it"},
    },
)
async def delete_certification(
    certification_id: int,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> None:
    cert = await session.get(Certification, certification_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="No certification with that id")

    await session.delete(cert)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Certification still has officer_certifications referencing it",
        )

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CertificationDeleted",
        aggregate_type="certification",
        aggregate_id=certification_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"certification_id": certification_id},
    )
