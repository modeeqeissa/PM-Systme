"""FR-AUD-04: the external_system_logs retention purge job.

Integration logs are 180-day operational data — the worker deletes rows past
the configured window and leaves everything within it alone.
"""
import datetime as dt
import uuid

from sqlalchemy import select

from app.models import ExternalSystemLog
from app.services.retention import RetentionWorker
from tests.conftest import SessionLocal

UTC = dt.timezone.utc


async def _make_log(*, age_days: int) -> int:
    async with SessionLocal() as s:
        row = ExternalSystemLog(
            system_name="CAD",
            direction="outbound",
            correlation_id=uuid.uuid4(),
            response_status=200,
        )
        s.add(row)
        await s.flush()
        row.created_at = dt.datetime.now(UTC) - dt.timedelta(days=age_days)
        await s.commit()
        return row.id


async def _remaining_ids() -> set:
    async with SessionLocal() as s:
        return {r.id for r in (await s.scalars(select(ExternalSystemLog)))}


async def test_purges_logs_past_the_retention_window(monkeypatch):
    monkeypatch.setenv("INTEGRATION_GATEWAY_LOG_RETENTION_DAYS", "180")
    old = await _make_log(age_days=181)
    fresh = await _make_log(age_days=179)

    removed = await RetentionWorker(SessionLocal).run_once()
    assert removed == 1

    remaining = await _remaining_ids()
    assert old not in remaining
    assert fresh in remaining


async def test_within_window_row_is_not_deleted(monkeypatch):
    monkeypatch.setenv("INTEGRATION_GATEWAY_LOG_RETENTION_DAYS", "180")
    keep = await _make_log(age_days=30)
    assert await RetentionWorker(SessionLocal).run_once() == 0
    assert keep in await _remaining_ids()


async def test_retention_period_is_configurable(monkeypatch):
    monkeypatch.setenv("INTEGRATION_GATEWAY_LOG_RETENTION_DAYS", "14")
    await _make_log(age_days=15)
    assert await RetentionWorker(SessionLocal).run_once() == 1
