import pytest

from app.models import NotificationPreference
from app.services.channels.dev import DevChannel
from app.services.delivery import DeliveryWorker
from app.services.templates import TemplateError, render


async def test_render_reads_body_from_db_and_fills_variables():
    from tests.conftest import SessionLocal

    async with SessionLocal() as s:
        subject, body = await render(
            s, "CERT_EXPIRING", {"certification_id": 7, "expires_date": "2026-09-15"}
        )
    assert "certification_id=7" in body
    assert "2026-09-15" in body
    assert subject == "Certification expiring soon"


async def test_render_unknown_template_raises():
    from tests.conftest import SessionLocal

    async with SessionLocal() as s:
        with pytest.raises(TemplateError):
            await render(s, "NOT_A_REAL_TEMPLATE", {})


async def test_delivery_worker_sends_queued_notification_via_dev_channel(
    make_notification,
):
    n = await make_notification(
        template_code="ACCOUNT_LOCKED_OUT", payload={}, status="queued"
    )
    dev = DevChannel()
    from tests.conftest import SessionLocal

    worker = DeliveryWorker(SessionLocal, channels={"in_app": dev})
    handled = await worker.run_once()
    assert handled == 1
    assert len(dev.sent) == 1
    assert dev.sent[0]["recipient_user_id"] == str(n.recipient_user_id)
    assert "locked" in dev.sent[0]["rendered_body"].lower()


async def test_delivery_worker_marks_notification_sent(make_notification):
    n = await make_notification(template_code="LEAVE_APPROVED", payload={}, status="queued")
    from tests.conftest import SessionLocal
    from app.models import Notification

    worker = DeliveryWorker(SessionLocal)
    await worker.run_once()

    async with SessionLocal() as s:
        row = await s.get(Notification, n.id)
    assert row.status == "sent"


async def test_delivery_worker_marks_unrenderable_notification_failed(make_notification):
    n = await make_notification(
        template_code="CERT_EXPIRING", payload={}, status="queued"  # missing required vars
    )
    from tests.conftest import SessionLocal
    from app.models import Notification

    worker = DeliveryWorker(SessionLocal)
    await worker.run_once()

    async with SessionLocal() as s:
        row = await s.get(Notification, n.id)
    assert row.status == "failed"


async def test_delivery_worker_ignores_already_sent_notifications(make_notification):
    await make_notification(status="sent")
    from tests.conftest import SessionLocal

    worker = DeliveryWorker(SessionLocal)
    handled = await worker.run_once()
    assert handled == 0


async def test_delivery_worker_suppresses_channel_disabled_by_preference(make_notification):
    import uuid

    from tests.conftest import SessionLocal
    from app.models import Notification

    user_id = uuid.uuid4()
    n = await make_notification(
        recipient_user_id=user_id, channel="in_app",
        template_code="LEAVE_APPROVED", payload={}, status="queued",
    )
    async with SessionLocal() as s:
        s.add(NotificationPreference(user_id=user_id, channel="in_app", enabled=False))
        await s.commit()

    dev = DevChannel()
    worker = DeliveryWorker(SessionLocal, channels={"in_app": dev})
    handled = await worker.run_once()
    assert handled == 1
    assert dev.sent == []  # never handed to the channel

    async with SessionLocal() as s:
        row = await s.get(Notification, n.id)
    assert row.status == "failed"  # terminal, not retried


async def test_delivery_worker_delivers_when_a_different_channel_is_disabled(make_notification):
    import uuid

    from tests.conftest import SessionLocal
    from app.models import Notification

    user_id = uuid.uuid4()
    n = await make_notification(
        recipient_user_id=user_id, channel="in_app",
        template_code="LEAVE_APPROVED", payload={}, status="queued",
    )
    async with SessionLocal() as s:
        s.add(NotificationPreference(user_id=user_id, channel="email", enabled=False))
        await s.commit()

    worker = DeliveryWorker(SessionLocal)
    await worker.run_once()
    async with SessionLocal() as s:
        row = await s.get(Notification, n.id)
    assert row.status == "sent"
