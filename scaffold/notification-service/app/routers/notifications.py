"""A user's own notifications — FR-NOTIF-01/03.

Self-scoped by the caller's JWT `sub` (identity_db.users.id), which is
exactly what notifications.recipient_user_id stores — no RBAC permission
code gates these; every authenticated user can read their own notifications,
the same way they can read their own profile. Notifications are never
created via this router — only the Kafka consumer (app.events.consumer)
creates them.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, get_token_claims
from app.models import Notification
from app.schemas import NotificationOut, NotificationStatus

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=list[NotificationOut],
    responses={401: {"description": "Missing or invalid access token"}},
)
async def list_my_notifications(
    status_: NotificationStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_token_claims),
) -> list[NotificationOut]:
    recipient_user_id = uuid.UUID(claims["sub"])
    q = (
        select(Notification)
        .where(Notification.recipient_user_id == recipient_user_id)
        .order_by(Notification.id.desc())
    )
    if status_ is not None:
        q = q.where(Notification.status == status_.value)
    rows = (await session.scalars(q)).all()
    return [NotificationOut.model_validate(n) for n in rows]


@router.get(
    "/{notification_id}",
    response_model=NotificationOut,
    responses={
        401: {"description": "Missing or invalid access token"},
        404: {"description": "No notification with that id for the caller"},
    },
)
async def get_my_notification(
    notification_id: int,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_token_claims),
) -> NotificationOut:
    recipient_user_id = uuid.UUID(claims["sub"])
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.recipient_user_id != recipient_user_id:
        raise HTTPException(
            status_code=404, detail="No notification with that id for the caller"
        )
    return NotificationOut.model_validate(notification)
