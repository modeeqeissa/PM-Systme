"""Background sweep that keeps officer_certifications.status current (FR-TRAIN-03).

Mirrors app.events.relay's poll-loop shape: a long-lived asyncio task, started
in the app lifespan, disabled via TRAINING_RECOMPUTE_ENABLED=0 (tests drive the
recompute logic directly through the API instead).
"""
import asyncio
import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.events import enqueue
from app.models import OfficerCertification
from app.services.expiry import compute_status

log = logging.getLogger("training-service.recompute-task")


class RecomputeTask:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def sweep_once(self) -> int:
        """Recompute every officer_certification's status. Returns how many changed."""
        lead_days = config.expiry_lead_days()
        today = dt.date.today()
        async with self._sessionmaker() as session:
            rows = (await session.scalars(select(OfficerCertification))).all()
            updated = 0
            for row in rows:
                new_status = compute_status(row.expires_date, today=today, lead_days=lead_days)
                if new_status != row.status:
                    old_status = row.status
                    row.status = new_status
                    enqueue(
                        session,
                        event_type="OfficerCertificationStatusChanged",
                        aggregate_type="officer_certification",
                        aggregate_id=row.id,
                        actor_id=None,
                        actor_role="system:recompute-task",
                        payload={
                            "officer_certification_id": str(row.id),
                            "officer_id": str(row.officer_id),
                            "from_status": old_status,
                            "to_status": new_status,
                        },
                    )
                    updated += 1
            await session.commit()
            return updated

    async def run_forever(self) -> None:
        poll = config.recompute_poll_seconds()
        while not self._stopping.is_set():
            try:
                await self.sweep_once()
            except Exception:  # keep the task alive across transient failures
                log.exception("certification expiry recompute sweep failed")
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
