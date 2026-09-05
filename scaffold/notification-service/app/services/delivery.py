"""Delivery worker: picks up queued notifications and attempts delivery
(FR-NOTIF-03: record delivery status for auditability).

Mirrors the outbox relay / recompute task poll-loop shape used elsewhere in
the platform. No HTTP trigger is exposed for this — unlike training/
community's recompute-status endpoints, there is no natural RBAC subject for
"deliver notifications now" (docs Section 2.3 names no notification-service
role), so it only runs as a background task; tests drive it directly via
``run_once``.
"""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.models import Notification, NotificationPreference
from app.services.channels.base import DeliveryError, NotificationChannel
from app.services.channels.dev import DevChannel
from app.services.templates import TemplateError, render

log = logging.getLogger("notification-service.delivery-worker")


def default_channels() -> dict[str, NotificationChannel]:
    """Every channel name maps to the same DevChannel instance until a real
    provider exists per channel (TD-004)."""
    dev = DevChannel()
    return {"email": dev, "sms": dev, "push": dev, "in_app": dev}


class DeliveryWorker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        channels: dict[str, NotificationChannel] | None = None,
        batch_size: int = 100,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._channels = channels if channels is not None else default_channels()
        self._batch_size = batch_size
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    @property
    def channels(self) -> dict[str, NotificationChannel]:
        return self._channels

    async def run_once(self) -> int:
        """Attempt delivery of every queued notification. Returns how many
        transitioned to sent or failed."""
        async with self._sessionmaker() as session:
            rows = (
                await session.scalars(
                    select(Notification)
                    .where(Notification.status == "queued")
                    .order_by(Notification.id)
                    .limit(self._batch_size)
                )
            ).all()
            handled = 0
            for row in rows:
                # FR-NOTIF-02: a row explicitly disabling this channel for this
                # user suppresses delivery. No 'suppressed' status exists in
                # SRS §9.3.8's enum, so it lands as 'failed' with a logged
                # reason — terminal, not retried.
                pref = await session.scalar(
                    select(NotificationPreference).where(
                        NotificationPreference.user_id == row.recipient_user_id,
                        NotificationPreference.channel == row.channel,
                    )
                )
                if pref is not None and not pref.enabled:
                    log.info(
                        "notification %s suppressed: recipient disabled channel %s",
                        row.id, row.channel,
                    )
                    row.status = "failed"
                    handled += 1
                    continue

                channel = self._channels.get(row.channel)
                try:
                    if channel is None:
                        raise DeliveryError(f"no channel registered for {row.channel!r}")
                    subject, body = await render(session, row.template_code, row.payload)
                    await channel.send(
                        recipient_user_id=row.recipient_user_id,
                        channel=row.channel,
                        subject=subject,
                        rendered_body=body,
                    )
                    row.status = "sent"
                except (DeliveryError, TemplateError):
                    log.exception("delivery failed for notification %s", row.id)
                    row.status = "failed"
                handled += 1
            await session.commit()
            return handled

    async def run_forever(self) -> None:
        poll = config.delivery_poll_seconds()
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("delivery worker pass failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=poll)
            except asyncio.TimeoutError:
                pass

    def spawn(self) -> None:
        self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
