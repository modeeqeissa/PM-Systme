"""Course assessments + graded results — docs §9.3.5.

`assessment_results.passed` is derived server-side from
`assessments.passing_score` **at grading time** (score >= passing_score) and
stored, so a later change to the assessment's passing_score never rewrites an
already-graded result.

Certification coupling — deliberate decision: recording a passing result does
**not** auto-issue an `officer_certification`. The SRS models certifications as
issued explicitly (`POST /officer-certifications`), and there is no schema link
saying "assessment X + session Y grants certification Z" — inventing one would
be schema invention (CLAUDE.md rule 5). A pass is also necessary-not-sufficient
(attendance, practical sign-off). So certification issuance stays a separate,
explicit Training-Officer action; the result event carries `course_id` so a
follow-up issue is one step.

Gated on `training.cert.*` — this service's domain-wide read/write code.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Assessment, AssessmentResult, Course
from app.schemas import (
    AssessmentCreate,
    AssessmentOut,
    AssessmentResultCreate,
    AssessmentResultOut,
)

by_course_router = APIRouter(
    prefix="/courses/{course_id}/assessments", tags=["assessments"]
)
router = APIRouter(prefix="/assessments", tags=["assessments"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_course_router.post(
    "",
    response_model=AssessmentOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No course with that id"},
    },
)
async def create_assessment(
    course_id: int,
    payload: AssessmentCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> AssessmentOut:
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="No course with that id")

    assessment = Assessment(
        course_id=course_id, title=payload.title, passing_score=payload.passing_score
    )
    session.add(assessment)
    await session.flush()
    await session.refresh(assessment)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="AssessmentCreated",
        aggregate_type="assessment",
        aggregate_id=assessment.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "assessment_id": str(assessment.id),
            "course_id": course_id,
            "title": assessment.title,
            "passing_score": str(assessment.passing_score),
        },
    )
    return AssessmentOut.model_validate(assessment)


@by_course_router.get(
    "",
    response_model=list[AssessmentOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No course with that id"},
    },
)
async def list_course_assessments(
    course_id: int,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[AssessmentOut]:
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="No course with that id")
    rows = (
        await session.scalars(
            select(Assessment).where(Assessment.course_id == course_id).order_by(Assessment.title)
        )
    ).all()
    return [AssessmentOut.model_validate(a) for a in rows]


@router.get(
    "/{assessment_id}",
    response_model=AssessmentOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No assessment with that id"},
    },
)
async def get_assessment(
    assessment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> AssessmentOut:
    assessment = await session.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="No assessment with that id")
    return AssessmentOut.model_validate(assessment)


@router.get(
    "/{assessment_id}/results",
    response_model=list[AssessmentResultOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No assessment with that id"},
    },
)
async def list_assessment_results(
    assessment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[AssessmentResultOut]:
    if await session.get(Assessment, assessment_id) is None:
        raise HTTPException(status_code=404, detail="No assessment with that id")
    rows = (
        await session.scalars(
            select(AssessmentResult)
            .where(AssessmentResult.assessment_id == assessment_id)
            .order_by(AssessmentResult.taken_at.desc())
        )
    ).all()
    return [AssessmentResultOut.model_validate(r) for r in rows]


@router.post(
    "/{assessment_id}/results",
    response_model=AssessmentResultOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No assessment with that id"},
    },
)
async def record_assessment_result(
    assessment_id: uuid.UUID,
    payload: AssessmentResultCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> AssessmentResultOut:
    assessment = await session.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="No assessment with that id")

    passed = payload.score >= assessment.passing_score

    result = AssessmentResult(
        assessment_id=assessment_id,
        officer_id=payload.officer_id,
        score=payload.score,
        passed=passed,
    )
    session.add(result)
    await session.flush()
    await session.refresh(result)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="AssessmentResultRecorded",
        aggregate_type="assessment_result",
        aggregate_id=result.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "assessment_result_id": str(result.id),
            "assessment_id": str(assessment_id),
            "course_id": assessment.course_id,
            "officer_id": str(result.officer_id),
            "score": str(result.score),
            "passing_score": str(assessment.passing_score),
            "passed": passed,
        },
    )
    return AssessmentResultOut.model_validate(result)
