"""POST /evidence, GET /evidence/{id}, POST /evidence/{id}/verify (FR-EVID-01/02/06).

Logging an item enqueues an EvidenceLogged domain event (transactional outbox);
audit-service consumes it and writes the independent, hash-chained audit-log
entry (CLAUDE.md rule 3 / FR-AUD-01).
"""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import CustodyEvent, EvidenceItem
from app.schemas import EvidenceItemOut, HashVerification
from app.services import vault

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=EvidenceItemOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks evidence.vault.write"},
    },
)
async def log_evidence_item(
    case_id: uuid.UUID = Form(...),
    item_type: str = Form(..., max_length=50),
    description: str = Form(...),
    collected_by: uuid.UUID = Form(...),
    collected_at: dt.datetime = Form(...),
    file: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("evidence.vault.write")),
) -> EvidenceItemOut:
    """Log an evidence item. A digital ``file`` is SHA-256 hashed (FR-EVID-02) and
    stored encrypted (FR-EVID-05); a ``collected`` custody event is recorded
    automatically (FR-EVID-03)."""
    storage_ref: str | None = None
    sha256_hash: str | None = None
    if file is not None:
        data = await file.read()
        sha256_hash = vault.sha256_hex(data)
        storage_ref = vault.store(data)

    item = EvidenceItem(
        case_id=case_id,
        item_type=item_type,
        description=description,
        collected_by=collected_by,
        collected_at=collected_at,
        storage_ref=storage_ref,
        sha256_hash=sha256_hash,
    )
    session.add(item)
    await session.flush()

    session.add(
        CustodyEvent(
            evidence_id=item.id,
            action="collected",
            from_officer=None,
            to_officer=collected_by,
            occurred_at=collected_at,
        )
    )
    await session.flush()
    await session.refresh(item)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="EvidenceLogged",
        aggregate_type="evidence_item",
        aggregate_id=item.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "evidence_id": str(item.id),
            "case_id": str(item.case_id),
            "item_type": item.item_type,
            "collected_by": str(item.collected_by),
            "sha256_hash": item.sha256_hash,
            "has_file": item.storage_ref is not None,
        },
    )
    return EvidenceItemOut.model_validate(item)


@router.get(
    "/{evidence_id}",
    response_model=EvidenceItemOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks evidence.vault.read"},
        404: {"description": "No such evidence item"},
    },
)
async def get_evidence_item(
    evidence_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("evidence.vault.read")),
) -> EvidenceItemOut:
    item = await session.get(EvidenceItem, evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such evidence item")
    return EvidenceItemOut.model_validate(item)


@router.post(
    "/{evidence_id}/verify",
    response_model=HashVerification,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks evidence.vault.read"},
        404: {"description": "No such evidence item"},
        409: {"description": "Item has no stored digital file to verify"},
    },
)
async def verify_evidence_hash(
    evidence_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("evidence.vault.read")),
) -> HashVerification:
    """Recompute the stored file's SHA-256 and compare to the upload hash (FR-EVID-06).

    A mismatch enqueues an ``EvidenceHashMismatch`` domain event (transactional
    outbox) so audit-service records the tamper detection and dashboard-service's
    ``mv_evidence_integrity.hash_mismatch_count`` reflects it.
    """
    item = await session.get(EvidenceItem, evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such evidence item")
    if not item.storage_ref or not item.sha256_hash:
        raise HTTPException(status_code=409, detail="No stored digital file to verify")
    if not vault.exists(item.storage_ref):
        raise HTTPException(status_code=409, detail="Stored file is missing from the vault")

    computed = vault.sha256_hex(vault.load(item.storage_ref))
    verified_at = dt.datetime.now(dt.timezone.utc)
    match = computed == item.sha256_hash

    if not match:
        actor_id, actor_role = _actor(claims)
        enqueue(
            session,
            event_type="EvidenceHashMismatch",
            aggregate_type="evidence_item",
            aggregate_id=item.id,
            actor_id=actor_id,
            actor_role=actor_role,
            payload={
                "evidence_id": str(item.id),
                "case_id": str(item.case_id),
                "stored_hash": item.sha256_hash,
                "computed_hash": computed,
                "verified_at": verified_at.isoformat(),
            },
        )

    return HashVerification(
        evidence_id=item.id,
        stored_hash=item.sha256_hash,
        computed_hash=computed,
        match=match,
        verified_at=verified_at,
    )
