"""A user's own notification channel preferences — FR-NOTIF-02.

Self-scoped by the caller's JWT `sub` (identity_db.users.id), same as
GET /notifications — no RBAC permission code. Absence of a row for a
channel means it's enabled (the delivery worker's default).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, get_token_claims
from app.models import NotificationPreference
from app.schemas import NotificationPreferenceOut, NotificationPreferenceUpsert

router = APIRouter(prefix="/notification-preferences", tags=["notification-preferences"])


@router.get(
    "",
    response_model=list[NotificationPreferenceOut],
    responses={401: {"description": "Missing or invalid access token"}},
)
async def list_my_preferences(
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_token_claims),
) -> list[NotificationPreferenceOut]:
    user_id = uuid.UUID(claims["sub"])
    rows = (
        await session.scalars(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
            .order_by(NotificationPreference.channel)
        )
    ).all()
    return [NotificationPreferenceOut.model_validate(r) for r in rows]


@router.put(
    "",
    response_model=NotificationPreferenceOut,
    responses={401: {"description": "Missing or invalid access token"}},
)
async def set_my_preference(
    payload: NotificationPreferenceUpsert,
    session: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_token_claims),
) -> NotificationPreferenceOut:
    user_id = uuid.UUID(claims["sub"])
    stmt = insert(NotificationPreference).values(
        user_id=user_id, channel=payload.channel.value, enabled=payload.enabled
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_notification_preferences_user_channel",
        set_={"enabled": stmt.excluded.enabled},
    )
    await session.execute(stmt)
    row = await session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.channel == payload.channel.value,
        )
    )
    return NotificationPreferenceOut.model_validate(row)
