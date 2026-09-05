"""Officer certification issuance + expiry tracking — FR-TRAIN-02/03.

officer_id is a logical reference into hr_db.officers (CLAUDE.md rule 1: no
cross-service DB access) — it is accepted as given, not validated against
another service's database. expires_date and status are always computed
server-side (app.services.expiry) so they can never drift from the linked
course's declared validity_months.
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Certification, Course, OfficerCertification
from app.schemas import (
    CertificationStatus,
    OfficerCertificationCreate,
    OfficerCertificationOut,
    RecomputeResult,
)
from app.services.expiry import compute_expires_date, compute_status

router = APIRouter(prefix="/officer-certifications", tags=["officer-certifications"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=OfficerCertificationOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "certification_id does not exist"},
    },
)
async def issue_officer_certification(
    payload: OfficerCertificationCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> OfficerCertificationOut:
    cert = await session.get(Certification, payload.certification_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="certification_id does not exist")
    course = await session.get(Course, cert.course_id)

    issued_date = payload.issued_date or dt.date.today()
    expires_date = compute_expires_date(issued_date, course.validity_months)
    status = compute_status(
        expires_date, today=dt.date.today(), lead_days=config.expiry_lead_days()
    )

    officer_cert = OfficerCertification(
        officer_id=payload.officer_id,
        certification_id=payload.certification_id,
        issued_date=issued_date,
        expires_date=expires_date,
        status=status,
    )
    session.add(officer_cert)
    await session.flush()
    await session.refresh(officer_cert)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="OfficerCertificationIssued",
        aggregate_type="officer_certification",
        aggregate_id=officer_cert.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "officer_certification_id": str(officer_cert.id),
            "officer_id": str(officer_cert.officer_id),
            "certification_id": officer_cert.certification_id,
            "issued_date": issued_date.isoformat(),
            "expires_date": expires_date.isoformat(),
            "status": status,
        },
    )
    return OfficerCertificationOut.model_validate(officer_cert)


@router.get(
    "",
    response_model=list[OfficerCertificationOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks training.cert.read"}},
)
async def list_officer_certifications(
    officer_id: uuid.UUID | None = Query(default=None),
    status_: CertificationStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[OfficerCertificationOut]:
    q = select(OfficerCertification).order_by(OfficerCertification.expires_date)
    if officer_id is not None:
        q = q.where(OfficerCertification.officer_id == officer_id)
    if status_ is not None:
        q = q.where(OfficerCertification.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [OfficerCertificationOut.model_validate(r) for r in rows]


@router.get(
    "/{officer_certification_id}",
    response_model=OfficerCertificationOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No officer certification with that id"},
    },
)
async def get_officer_certification(
    officer_certification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> OfficerCertificationOut:
    row = await session.get(OfficerCertification, officer_certification_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="No officer certification with that id"
        )
    return OfficerCertificationOut.model_validate(row)


@router.post(
    "/recompute-status",
    response_model=RecomputeResult,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
    },
)
async def recompute_officer_certification_statuses(
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> RecomputeResult:
    """On-demand sweep (FR-TRAIN-03): recompute every officer_certification's
    status against today's date. The same recompute also runs periodically in
    the background (app.services.recompute_task, TRAINING_RECOMPUTE_ENABLED)."""
    today = dt.date.today()
    lead_days = config.expiry_lead_days()
    actor_id, actor_role = _actor(claims)

    rows = (await session.scalars(select(OfficerCertification))).all()
    updated = 0
    for row in rows:
        new_status = compute_status(row.expires_date, today=today, lead_days=lead_days)
        if new_status != row.status:
            old_status = row.status
            row.status = new_status
            enqueue(
                session,
                event_type="OfficerCertificationStatusChanged",
                aggregate_type="officer_certification",
                aggregate_id=row.id,
                actor_id=actor_id,
                actor_role=actor_role,
                payload={
                    "officer_certification_id": str(row.id),
                    "officer_id": str(row.officer_id),
                    "from_status": old_status,
                    "to_status": new_status,
                },
            )
            updated += 1

    return RecomputeResult(checked=len(rows), updated=updated)
