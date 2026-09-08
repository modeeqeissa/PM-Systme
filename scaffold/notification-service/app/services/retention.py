"""Retention purge worker (FR-AUD-04 / docs §9.6).

Notifications are 90-day operational data — genuinely safe to delete. This is
the real scheduled purge job: rows whose ``created_at`` is older than the
configured window are removed. Mirrors the delivery-worker / outbox-relay
poll-loop shape used elsewhere; no HTTP trigger (docs Section 2.3 names no
notification-service role, same as delivery). Tests call ``run_once`` directly.

Per §9.6, delivery-*failure* records (status='failed') are kept longer — a
year — so an operator can still investigate a bad delivery well after the
routine 90-day window. 'suppressed' is an intentional opt-out, not a failure,
so it purges on the normal schedule.
"""
import asyncio
import datetime as dt
import logging

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.models import Notification
from app.services import settings

log = logging.getLogger("notification-service.retention-worker")

# §9.6: delivery-failure records are retained a year, not the routine 90 days.
_FAILED_RETENTION_DAYS = 365


class RetentionWorker:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def run_once(self) -> int:
        """Purge notifications past their retention window (§9.6):
        status='failed' rows after a year, everything else after the
        configured operational window. Returns the row count removed."""
        now = dt.datetime.now(dt.timezone.utc)
        routine_days = settings.get("retention_days")
        routine_cutoff = now - dt.timedelta(days=routine_days)
        failed_cutoff = now - dt.timedelta(days=_FAILED_RETENTION_DAYS)
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(Notification).where(
                    or_(
                        (Notification.status != "failed")
                        & (Notification.created_at < routine_cutoff),
                        (Notification.status == "failed")
                        & (Notification.created_at < failed_cutoff),
                    )
                )
            )
            await session.commit()
            removed = result.rowcount or 0
            if removed:
                log.info(
                    "retention: purged %d notification(s) "
                    "(routine window %dd, failed-delivery window %dd)",
                    removed, routine_days, _FAILED_RETENTION_DAYS,
                )
            return removed

    async def run_forever(self) -> None:
        poll = config.retention_poll_seconds()
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("retention worker pass failed")
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
