"""Outbox relay: publish unpublished outbox rows to Kafka, mark them sent.

At-least-once: a crash after ``send_and_wait`` but before the row is marked
published re-sends on the next pass; consumers dedupe on ``event_id``.
"""
import asyncio
import json
import logging

from aiokafka import AIOKafkaProducer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.config import kafka_bootstrap, relay_poll_seconds
from app.events.models import OutboxEvent

log = logging.getLogger("community-service.outbox-relay")


class OutboxRelay:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        bootstrap: str | None = None,
        batch_size: int = 100,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._bootstrap = bootstrap or kafka_bootstrap()
        self._batch_size = batch_size
        self._producer: AIOKafkaProducer | None = None
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            enable_idempotence=True,
            acks="all",
        )
        await self._producer.start()

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def drain_once(self) -> int:
        """Publish one batch of unpublished events. Returns how many were sent."""
        assert self._producer is not None, "start() first"
        async with self._sessionmaker() as session:
            rows = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            sent = 0
            for row in rows:
                await self._producer.send_and_wait(
                    row.topic,
                    json.dumps(row.body).encode(),
                    key=row.aggregate_id.encode(),
                )
                row.published_at = _utcnow()
                row.attempts += 1
                sent += 1
            await session.commit()
            return sent

    async def run_forever(self) -> None:
        poll = relay_poll_seconds()
        while not self._stopping.is_set():
            try:
                published = await self.drain_once()
            except Exception:  # keep the relay alive across transient failures
                log.exception("outbox relay drain failed")
                published = 0
            if published == 0:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=poll)
                except asyncio.TimeoutError:
                    pass

    def spawn(self) -> None:
        self._task = asyncio.create_task(self.run_forever())


def _utcnow():
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc)
