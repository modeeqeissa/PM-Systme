"""Person master records — docs §9.3.2 (revised).

`persons` is the real record behind `arrests.suspect_id` and (optionally)
`statements.person_id`. CRUD + a name/national_id search that pairs with case
search (FR-CASE-08). Every mutation enqueues a domain event in the same DB
transaction (transactional outbox); audit-service consumes those and writes the
hash-chained audit-log entry (CLAUDE.md rule 3).

Permission codes: persons are case-domain data, so this reuses the existing
`case.*` codes rather than inventing `person.*` — `case.read` to search/read,
`case.write` to create/update, `case.approve` (supervisory) to delete. This
mirrors the FR-CASE-07 decision to reuse `case.approve` for officer staffing
rather than add a `case.assign` code (docs §4.1 enumerates case actions as
read / write / approve / export only).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Arrest, CasePerson, Person, Statement
from app.schemas import PersonCreate, PersonOut, PersonUpdate

router = APIRouter(prefix="/persons", tags=["persons"])

_TRACKED_FIELDS = (
    "first_name",
    "last_name",
    "date_of_birth",
    "national_id",
    "gender",
    "address",
    "phone",
    "notes",
)


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


def _summary(person: Person) -> dict:
    """Non-sensitive identifying fields for the event payload / audit metadata."""
    return {
        "person_id": str(person.id),
        "name": f"{person.first_name} {person.last_name}",
        "national_id": person.national_id,
    }


@router.post(
    "",
    response_model=PersonOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.write"},
        409: {"description": "national_id already belongs to another person"},
    },
)
async def create_person(
    payload: PersonCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.write")),
) -> PersonOut:
    """Create a person master record. `national_id`, when given, must be unique
    (the practical de-duplication key — docs §9.3.2)."""
    person = Person(**payload.model_dump())
    session.add(person)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="national_id already belongs to another person"
        )
    await session.refresh(person)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PersonCreated",
        aggregate_type="person",
        aggregate_id=person.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload=_summary(person),
    )
    return PersonOut.model_validate(person)


@router.get(
    "",
    response_model=list[PersonOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.read"},
    },
)
async def search_persons(
    q: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
        description="Case-insensitive substring match on first or last name",
    ),
    national_id: str | None = Query(default=None, max_length=50, description="Exact match"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("case.read")),
) -> list[PersonOut]:
    """Search persons by name and/or exact national_id (FR-CASE-08 companion).

    With no filter, returns the most recently created persons — this backs the
    "search existing or create new" flow on the arrest / statement forms.
    """
    stmt = select(Person).order_by(Person.created_at.desc()).limit(limit).offset(offset)
    if q is not None:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Person.first_name).like(needle),
                func.lower(Person.last_name).like(needle),
            )
        )
    if national_id is not None:
        stmt = stmt.where(Person.national_id == national_id)

    rows = (await session.scalars(stmt)).all()
    return [PersonOut.model_validate(p) for p in rows]


@router.get(
    "/{person_id}",
    response_model=PersonOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.read"},
        404: {"description": "No person with that id"},
    },
)
async def get_person(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("case.read")),
) -> PersonOut:
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No person with that id")
    return PersonOut.model_validate(person)


@router.patch(
    "/{person_id}",
    response_model=PersonOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.write"},
        404: {"description": "No person with that id"},
        409: {"description": "national_id already belongs to another person"},
    },
)
async def update_person(
    person_id: uuid.UUID,
    payload: PersonUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.write")),
) -> PersonOut:
    """Partial update — only fields present in the request body are changed."""
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No person with that id")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return PersonOut.model_validate(person)

    changed_fields = sorted(k for k in changes if k in _TRACKED_FIELDS)
    for key, value in changes.items():
        setattr(person, key, value)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="national_id already belongs to another person"
        )
    await session.refresh(person)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PersonUpdated",
        aggregate_type="person",
        aggregate_id=person.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={**_summary(person), "changed_fields": changed_fields},
    )
    return PersonOut.model_validate(person)


@router.delete(
    "/{person_id}",
    status_code=204,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks case.approve"},
        404: {"description": "No person with that id"},
        409: {"description": "Person is still referenced by an arrest, statement or case link"},
    },
)
async def delete_person(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("case.approve")),
) -> None:
    """Delete a person master record.

    Blocked (409) while the person is still referenced by an arrest
    (`suspect_id`, NOT NULL), a statement (`person_id`), or a `case_persons`
    link — those references must be cleared first. Deleting is a supervisory
    action (`case.approve`) because it removes an identity other records point
    at; the delete itself is audited via `PersonDeleted`.
    """
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No person with that id")

    refs = {
        "arrests": await session.scalar(
            select(func.count()).select_from(Arrest).where(Arrest.suspect_id == person_id)
        ),
        "statements": await session.scalar(
            select(func.count()).select_from(Statement).where(Statement.person_id == person_id)
        ),
        "case_links": await session.scalar(
            select(func.count()).select_from(CasePerson).where(CasePerson.person_id == person_id)
        ),
    }
    if any(refs.values()):
        raise HTTPException(
            status_code=409,
            detail=(
                "Person is still referenced "
                f"(arrests={refs['arrests']}, statements={refs['statements']}, "
                f"case_links={refs['case_links']}) — clear those first"
            ),
        )

    summary = _summary(person)
    await session.delete(person)
    await session.flush()

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="PersonDeleted",
        aggregate_type="person",
        aggregate_id=person_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload=summary,
    )
    return None
