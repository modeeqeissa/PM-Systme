"""FR-AUD-04: the notification retention purge job.

Notifications are 90-day operational data — the worker deletes rows past the
configured window and leaves everything within it alone.
"""
import datetime as dt

from sqlalchemy import select

from app.models import Notification
from app.services.retention import RetentionWorker
from tests.conftest import SessionLocal

UTC = dt.timezone.utc


async def _remaining_ids() -> set:
    async with SessionLocal() as s:
        return {n.id for n in (await s.scalars(select(Notification)))}


async def test_purges_rows_past_the_retention_window(make_notification, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_RETENTION_DAYS", "90")
    now = dt.datetime.now(UTC)
    old = await make_notification(created_at=now - dt.timedelta(days=91))
    fresh = await make_notification(created_at=now - dt.timedelta(days=89))

    removed = await RetentionWorker(SessionLocal).run_once()
    assert removed == 1

    remaining = await _remaining_ids()
    assert old.id not in remaining
    assert fresh.id in remaining


async def test_within_window_row_is_not_deleted(make_notification):
    n = await make_notification(created_at=dt.datetime.now(UTC) - dt.timedelta(days=10))
    assert await RetentionWorker(SessionLocal).run_once() == 0
    assert n.id in await _remaining_ids()


async def test_retention_period_is_configurable(make_notification, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_RETENTION_DAYS", "7")
    await make_notification(created_at=dt.datetime.now(UTC) - dt.timedelta(days=8))
    assert await RetentionWorker(SessionLocal).run_once() == 1
