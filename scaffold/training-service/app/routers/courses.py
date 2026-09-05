"""Course catalog — FR-TRAIN-01.

Every mutating handler enqueues a domain event in the same DB transaction
(transactional outbox, SRS §3.4); audit-service consumes those events into
the independent, hash-chained audit log (CLAUDE.md rule 3 / FR-AUD-01).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Course
from app.schemas import CourseCreate, CourseOut, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@router.post(
    "",
    response_model=CourseOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
    },
)
async def create_course(
    payload: CourseCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> CourseOut:
    course = Course(
        title=payload.title,
        validity_months=payload.validity_months,
        mandatory=payload.mandatory,
    )
    session.add(course)
    await session.flush()
    await session.refresh(course)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CourseCreated",
        aggregate_type="course",
        aggregate_id=course.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "course_id": course.id,
            "title": course.title,
            "validity_months": course.validity_months,
            "mandatory": course.mandatory,
        },
    )
    return CourseOut.model_validate(course)


@router.get(
    "",
    response_model=list[CourseOut],
    responses={401: {"description": "Missing or invalid access token"},
               403: {"description": "Caller lacks training.cert.read"}},
)
async def list_courses(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[CourseOut]:
    rows = (await session.scalars(select(Course).order_by(Course.title))).all()
    return [CourseOut.model_validate(c) for c in rows]


@router.get(
    "/{course_id}",
    response_model=CourseOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No course with that id"},
    },
)
async def get_course(
    course_id: int,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> CourseOut:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="No course with that id")
    return CourseOut.model_validate(course)


@router.patch(
    "/{course_id}",
    response_model=CourseOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No course with that id"},
    },
)
async def update_course(
    course_id: int,
    payload: CourseUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> CourseOut:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="No course with that id")

    updated_fields: list[str] = []
    if payload.title is not None:
        course.title = payload.title
        updated_fields.append("title")
    if payload.validity_months is not None:
        course.validity_months = payload.validity_months
        updated_fields.append("validity_months")
    if payload.mandatory is not None:
        course.mandatory = payload.mandatory
        updated_fields.append("mandatory")

    await session.flush()
    await session.refresh(course)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CourseUpdated",
        aggregate_type="course",
        aggregate_id=course.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"course_id": course.id, "fields": updated_fields},
    )
    return CourseOut.model_validate(course)


@router.delete(
    "/{course_id}",
    status_code=204,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No course with that id"},
        409: {"description": "Course still has certifications referencing it"},
    },
)
async def delete_course(
    course_id: int,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> None:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="No course with that id")

    await session.delete(course)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Course still has certifications referencing it"
        )

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="CourseDeleted",
        aggregate_type="course",
        aggregate_id=course_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"course_id": course_id},
    )
