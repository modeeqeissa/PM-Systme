"""Communities — named neighbourhood/group per station (docs §9.3.4).

The unit meetings and engagement are organised around. Every mutating handler
enqueues a domain event in the same DB transaction (transactional outbox);
audit-service consumes those into the hash-chained audit log.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Community
from app.schemas import CommunityCreate, CommunityOut, CommunityUpdate

router = APIRouter(prefix="/communities", tags=["communities"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=CommunityOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
    },
)
async def create_community(
    payload: CommunityCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> CommunityOut:
    community = Community(
        name=payload.name,
        station_id=payload.station_id,
        description=payload.description,
    )
    session.add(community)
    await session.flush()
    await session.refresh(community)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CommunityCreated",
        aggregate_type="community",
        aggregate_id=community.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "community_id": str(community.id),
            "name": community.name,
            "station_id": str(community.station_id),
        },
    )
    return CommunityOut.model_validate(community)


@router.get(
    "",
    response_model=list[CommunityOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
    },
)
async def list_communities(
    station_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> list[CommunityOut]:
    q = select(Community).order_by(Community.name)
    if station_id is not None:
        q = q.where(Community.station_id == station_id)
    rows = (await session.scalars(q)).all()
    return [CommunityOut.model_validate(c) for c in rows]


@router.get(
    "/{community_id}",
    response_model=CommunityOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.read"},
        404: {"description": "No community with that id"},
    },
)
async def get_community(
    community_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("community.read")),
) -> CommunityOut:
    community = await session.get(Community, community_id)
    if community is None:
        raise HTTPException(status_code=404, detail="No community with that id")
    return CommunityOut.model_validate(community)


@router.patch(
    "/{community_id}",
    response_model=CommunityOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks community.write"},
        404: {"description": "No community with that id"},
    },
)
async def update_community(
    community_id: uuid.UUID,
    payload: CommunityUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("community.write")),
) -> CommunityOut:
    community = await session.get(Community, community_id)
    if community is None:
        raise HTTPException(status_code=404, detail="No community with that id")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return CommunityOut.model_validate(community)
    for key, value in changes.items():
        setattr(community, key, value)
    await session.flush()
    await session.refresh(community)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CommunityUpdated",
        aggregate_type="community",
        aggregate_id=community.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "community_id": str(community.id),
            "name": community.name,
            "changed_fields": sorted(changes),
        },
    )
    return CommunityOut.model_validate(community)
