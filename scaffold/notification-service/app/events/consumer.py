"""Kafka -> queued notifications. At-least-once, idempotent on event_id (SRS §9.4)."""
import asyncio
import json
import logging
import uuid

from aiokafka import AIOKafkaConsumer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.events.mapping import apply_event
from app.events.topics import consumed_topics
from app.models import ConsumedEvent

log = logging.getLogger("notification-service.consumer")


class NotificationConsumer:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        bootstrap: str | None = None,
        group_id: str | None = None,
        topics: list[str] | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._bootstrap = bootstrap or config.kafka_bootstrap()
        self._group_id = group_id or config.consumer_group()
        self._topics = topics or consumed_topics()
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def _handle(self, session: AsyncSession, envelope: dict) -> bool:
        try:
            event_id = uuid.UUID(str(envelope["event_id"]))
        except (KeyError, ValueError):
            log.warning("event without a usable event_id, skipping")
            return False
        if await session.get(ConsumedEvent, event_id) is not None:
            return False
        session.add(ConsumedEvent(event_id=event_id))
        return await apply_event(session, envelope)

    async def process_available(self, timeout: float = 8.0) -> int:
        """Consume whatever is available; return the count of notifications queued."""
        assert self._consumer is not None, "start() first"
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        queued = 0
        seen_any = False
        while loop.time() < deadline:
            batch = await self._consumer.getmany(timeout_ms=1000)
            if not batch:
                if seen_any:
                    break
                continue
            seen_any = True
            # Order the batch by occurred_at: OfficerSupervisorChanged depends
            # on its OfficerCreated (different topic), so per-partition order
            # alone isn't causal. Envelope timestamps are.
            envelopes = [
                json.loads(message.value)
                for _tp, messages in batch.items()
                for message in messages
            ]
            envelopes.sort(key=lambda e: e.get("occurred_at") or "")
            for envelope in envelopes:
                async with self._sessionmaker() as session:
                    try:
                        if await self._handle(session, envelope):
                            queued += 1
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
            await self._consumer.commit()
        return queued

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.process_available(timeout=1.0)
            except Exception:
                log.exception("notification consumer batch failed")
                await asyncio.sleep(1.0)

    def spawn(self) -> None:
        self._task = asyncio.create_task(self.run_forever())
