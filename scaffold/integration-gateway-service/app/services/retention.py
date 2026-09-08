"""Retention purge worker (FR-AUD-04 / docs §9.6).

external_system_logs are 180-day operational data — safe to delete. Rows whose
``created_at`` is older than the configured window are removed on a daily
poll. Mirrors the outbox-relay loop shape; no HTTP trigger. Tests call
``run_once`` directly.
"""
import asyncio
import datetime as dt
import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.models import ExternalSystemLog
from app.services import settings

log = logging.getLogger("integration-gateway-service.retention-worker")


class RetentionWorker:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def run_once(self) -> int:
        """Delete every external-system log older than the retention window.
        Returns the row count removed."""
        retention_days = settings.get("log_retention_days")
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retention_days)
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(ExternalSystemLog).where(ExternalSystemLog.created_at < cutoff)
            )
            await session.commit()
            removed = result.rowcount or 0
            if removed:
                log.info(
                    "retention: purged %d external_system_log row(s) older than %d days",
                    removed, retention_days,
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
