"""Course materials — FR-TRAIN-01 / docs §9.3.5.

Course documents, object-storage-backed (app.services.materials_store) the same
way evidence files are. `training.cert.*` is this service's domain-wide
read/write code (it gates courses and certifications too — the "Training
Officer" role is "Full CRUD on the Training domain", docs §2.3), so materials
reuse it rather than adding a `training.material.*` code.
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.events import enqueue
from app.models import Course, Material
from app.schemas import MaterialOut
from app.services import materials_store

by_course_router = APIRouter(prefix="/courses/{course_id}/materials", tags=["materials"])
router = APIRouter(prefix="/materials", tags=["materials"])


def _actor(claims: dict) -> tuple[str, str]:
    return claims.get("sub"), ",".join(claims.get("roles") or [])


@by_course_router.get(
    "",
    response_model=list[MaterialOut],
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No course with that id"},
    },
)
async def list_course_materials(
    course_id: int,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> list[MaterialOut]:
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="No course with that id")
    rows = (
        await session.scalars(
            select(Material).where(Material.course_id == course_id).order_by(Material.title)
        )
    ).all()
    return [MaterialOut.model_validate(m) for m in rows]


@by_course_router.post(
    "",
    response_model=MaterialOut,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No course with that id"},
    },
)
async def upload_course_material(
    course_id: int,
    title: str = Form(..., max_length=200),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> MaterialOut:
    """Upload a course document. The bytes are stored under an opaque `file_ref`
    (object-storage pattern); the row records the ref, not the content."""
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="No course with that id")

    data = await file.read()
    file_ref = materials_store.store(data)

    material = Material(course_id=course_id, title=title, file_ref=file_ref)
    session.add(material)
    await session.flush()
    await session.refresh(material)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="MaterialAdded",
        aggregate_type="material",
        aggregate_id=material.id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={
            "material_id": str(material.id),
            "course_id": course_id,
            "title": material.title,
        },
    )
    return MaterialOut.model_validate(material)


@router.get(
    "/{material_id}",
    response_model=MaterialOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.read"},
        404: {"description": "No material with that id"},
    },
)
async def get_material(
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_permission("training.cert.read")),
) -> MaterialOut:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="No material with that id")
    return MaterialOut.model_validate(material)


@router.delete(
    "/{material_id}",
    status_code=204,
    responses={
        401: {"description": "Missing or invalid access token"},
        403: {"description": "Caller lacks training.cert.write"},
        404: {"description": "No material with that id"},
    },
)
async def delete_material(
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(require_permission("training.cert.write")),
) -> None:
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="No material with that id")

    file_ref = material.file_ref
    await session.delete(material)
    await session.flush()
    materials_store.delete(file_ref)

    actor_id, actor_role = _actor(claims)
    enqueue(
        session,
        event_type="MaterialRemoved",
        aggregate_type="material",
        aggregate_id=material_id,
        actor_id=actor_id,
        actor_role=actor_role,
        payload={"material_id": str(material_id), "course_id": material.course_id},
    )
    return None
