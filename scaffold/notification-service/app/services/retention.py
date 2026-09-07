"""Retention purge worker (FR-AUD-04 / docs §9.6).

Notifications are 90-day operational data — genuinely safe to delete. This is
the real scheduled purge job: rows whose ``created_at`` is older than the
configured window are removed. Mirrors the delivery-worker / outbox-relay
poll-loop shape used elsewhere; no HTTP trigger (docs Section 2.3 names no
notification-service role, same as delivery). Tests call ``run_once`` directly.
"""
import asyncio
import datetime as dt
import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.models import Notification

log = logging.getLogger("notification-service.retention-worker")


class RetentionWorker:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def run_once(self) -> int:
        """Delete every notification older than the retention window. Returns
        the row count removed."""
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=config.retention_days())
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(Notification).where(Notification.created_at < cutoff)
            )
            await session.commit()
            removed = result.rowcount or 0
            if removed:
                log.info(
                    "retention: purged %d notification(s) older than %d days",
                    removed, config.retention_days(),
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
