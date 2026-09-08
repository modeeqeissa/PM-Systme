"""Partner organizations — NGOs, neighbourhood associations (docs §9.3.4).

Optionally tied to a community. Every mutating handler enqueues a domain event
in the same DB transaction (transactional outbox).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Community, Organization
from app.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


async def _require_community(session: AsyncSession, community_id: uuid.UUID | None) -> None:
    if community_id is not None and await session.get(Community, community_id) is None:
        raise HTTPException(status_code=404, detail="community_id does not exist")


@router.post(
    "",
    response_model=OrganizationOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "community_id does not exist"},
    },
)
async def create_organization(
    payload: OrganizationCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> OrganizationOut:
    await _require_community(session, payload.community_id)

    org = Organization(
        name=payload.name,
        community_id=payload.community_id,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
    )
    session.add(org)
    await session.flush()
    await session.refresh(org)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="OrganizationCreated",
        aggregate_type="organization",
        aggregate_id=org.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "organization_id": str(org.id),
            "name": org.name,
            "community_id": str(org.community_id) if org.community_id else None,
        },
    )
    return OrganizationOut.model_validate(org)


@router.get(
    "",
    response_model=list[OrganizationOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
    },
)
async def list_organizations(
    community_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[OrganizationOut]:
    q = select(Organization).order_by(Organization.name)
    if community_id is not None:
        q = q.where(Organization.community_id == community_id)
    rows = (await session.scalars(q)).all()
    return [OrganizationOut.model_validate(o) for o in rows]


@router.get(
    "/{organization_id}",
    response_model=OrganizationOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No organization with that id"},
    },
)
async def get_organization(
    organization_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> OrganizationOut:
    org = await session.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="No organization with that id")
    return OrganizationOut.model_validate(org)


@router.patch(
    "/{organization_id}",
    response_model=OrganizationOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No organization with that id, or community_id does not exist"},
    },
)
async def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> OrganizationOut:
    org = await session.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="No organization with that id")

    changes = payload.model_dump(exclude_unset=True)
    if "community_id" in changes:
        await _require_community(session, changes["community_id"])
    if not changes:
        return OrganizationOut.model_validate(org)
    for key, value in changes.items():
        setattr(org, key, value)
    await session.flush()
    await session.refresh(org)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="OrganizationUpdated",
        aggregate_type="organization",
        aggregate_id=org.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "organization_id": str(org.id),
            "name": org.name,
            "community_id": str(org.community_id) if org.community_id else None,
            "changed_fields": sorted(changes),
        },
    )
    return OrganizationOut.model_validate(org)
