"""Background sweep that flags overdue follow-up actions (FR-COMM-04).

Mirrors training-service's RecomputeTask / app.events.relay's poll-loop
shape: a long-lived asyncio task started in the app lifespan, disabled via
COMMUNITY_RECOMPUTE_ENABLED=0 (tests drive the recompute logic directly
through the API instead).
"""
import asyncio
import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.events import enqueue
from app.models import FollowUpAction
from app.services.overdue import is_overdue

log = logging.getLogger("community-service.recompute-task")


class RecomputeTask:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def sweep_once(self) -> int:
        """Flag every pending follow-up action past its due_date as overdue.
        Returns how many changed."""
        today = dt.date.today()
        async with self._sessionmaker() as session:
            rows = (
                await session.scalars(
                    select(FollowUpAction).where(FollowUpAction.status == "pending")
                )
            ).all()
            updated = 0
            for row in rows:
                if is_overdue(row.due_date, today=today):
                    row.status = "overdue"
                    enqueue(
                        session,
                        event_type="FollowUpActionStatusChanged",
                        aggregate_type="follow_up_action",
                        aggregate_id=row.id,
                        actor_id=None,
                        actor_role="system:recompute-task",
                        payload={
                            "follow_up_action_id": str(row.id),
                            "assigned_to": str(row.assigned_to),
                            "from_status": "pending",
                            "to_status": "overdue",
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
                log.exception("follow-up action overdue sweep failed")
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
