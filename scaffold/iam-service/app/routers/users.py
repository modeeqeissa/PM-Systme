"""/users/* — profile, account management, password, role assignment."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session, require_permission
from app.models import User
from app.schemas import CurrentUser, PasswordChange, RoleIdList
from app.schemas import User as UserOut
from app.schemas import UserCreate, UserUpdate
from app.services import users as svc
from app.services.rbac import effective_permissions, get_user
from app.services.users import load_roles

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=CurrentUser)
async def read_me(user: User = Depends(get_current_user)):
    return CurrentUser.from_model(user)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.user.write")),
):
    return UserOut.from_model(await svc.create_user(session, payload))


@router.get("/{user_id}", response_model=UserOut)
async def read_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.user.read")),
):
    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    return UserOut.from_model(user)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.user.write")),
):
    return UserOut.from_model(await svc.update_user(session, user_id, payload))


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    user_id: uuid.UUID,
    payload: PasswordChange,
    session: AsyncSession = Depends(get_session),
    caller: User = Depends(get_current_user),
):
    await svc.change_password(
        session,
        target_id=user_id,
        caller=caller,
        caller_can_manage="iam.user.write" in effective_permissions(caller),
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{user_id}/roles", response_model=CurrentUser)
async def set_user_roles(
    user_id: uuid.UUID,
    payload: RoleIdList,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission("iam.role.write")),
):
    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    user.roles = await load_roles(session, payload.role_ids)
    await session.flush()
    return CurrentUser.from_model(await get_user(session, user_id))
