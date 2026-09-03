"""/roles and /permissions — configurable RBAC (FR-IAM-03)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_permission
from app.models import Permission as PermissionModel
from app.models import Role as RoleModel
from app.models import User
from app.schemas import Permission, PermissionCodeList, Role, RoleCreate

router = APIRouter(tags=["rbac"])


@router.get("/roles", response_model=list[Role])
async def list_roles(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.role.read")),
):
    rows = (await session.scalars(select(RoleModel).order_by(RoleModel.id))).all()
    return [Role.from_model(r) for r in rows]


@router.post("/roles", response_model=Role, status_code=201)
async def create_role(
    payload: RoleCreate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.role.write")),
):
    # permissions=[] so the collection counts as loaded (no lazy IO after flush).
    role = RoleModel(name=payload.name, description=payload.description, permissions=[])
    session.add(role)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Role name already exists")
    return Role.from_model(role)


@router.put("/roles/{role_id}/permissions", response_model=Role)
async def set_role_permissions(
    role_id: int,
    payload: PermissionCodeList,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.role.write")),
):
    role = await session.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such role")
    wanted = set(payload.codes)
    perms = (
        await session.scalars(
            select(PermissionModel).where(PermissionModel.code.in_(wanted))
        )
    ).all()
    missing = wanted - {p.code for p in perms}
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown permission code(s): {sorted(missing)}"
        )
    role.permissions = list(perms)
    await session.flush()
    return Role.from_model(role)


@router.get("/permissions", response_model=list[Permission])
async def list_permissions(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.role.read")),
):
    rows = (
        await session.scalars(select(PermissionModel).order_by(PermissionModel.code))
    ).all()
    return [Permission.model_validate(p) for p in rows]
