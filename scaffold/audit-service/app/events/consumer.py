"""Kafka -> audit_logs. At-least-once delivery, idempotent on event_id (SRS §9.4)."""
import asyncio
import json
import logging
import uuid

from aiokafka import AIOKafkaConsumer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import config
from app.events.mapping import to_audit_fields
from app.events.topics import consumed_topics
from app.models import ConsumedEvent
from app.services.hashchain import append_entry

log = logging.getLogger("audit-service.consumer")


class AuditConsumer:
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
        """Write one audit entry for this event. Returns True if a row was added."""
        try:
            event_id = uuid.UUID(str(envelope["event_id"]))
        except (KeyError, ValueError):
            log.warning("event without a usable event_id, skipping: %r", envelope)
            return False

        already = await session.get(ConsumedEvent, event_id)
        if already is not None:
            return False

        fields = to_audit_fields(envelope)
        session.add(ConsumedEvent(event_id=event_id))
        if fields is None:
            log.info("no audit mapping for event_type=%s", envelope.get("event_type"))
            return False

        await append_entry(session, **fields)
        return True

    async def process_available(self, timeout: float = 8.0) -> int:
        """Consume whatever is currently available; return audit rows written.

        Polls repeatedly (a fresh consumer group needs a few polls to join and
        get its first fetch) until a poll comes back empty *after* data was seen,
        or ``timeout`` seconds elapse.
        """
        assert self._consumer is not None, "start() first"
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        written = 0
        seen_any = False
        while loop.time() < deadline:
            batch = await self._consumer.getmany(timeout_ms=1000)
            if not batch:
                if seen_any:
                    break
                continue
            seen_any = True
            for _tp, messages in batch.items():
                for message in messages:
                    envelope = json.loads(message.value)
                    async with self._sessionmaker() as session:
                        try:
                            if await self._handle(session, envelope):
                                written += 1
                            await session.commit()
                        except IntegrityError:
                            # concurrent duplicate for this event_id -> already done
                            await session.rollback()
            await self._consumer.commit()
        return written

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.process_available(timeout=1.0)
            except Exception:  # keep consuming across transient failures
                log.exception("audit consumer batch failed")
                await asyncio.sleep(1.0)

    def spawn(self) -> None:
        self._task = asyncio.create_task(self.run_forever())
