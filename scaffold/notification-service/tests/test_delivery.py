import pytest

from app.services.channels.dev import DevChannel
from app.services.delivery import DeliveryWorker
from app.services.templates import render


def test_render_fills_in_payload_variables():
    body = render("CERT_EXPIRING", {"certification_id": 7, "expires_date": "2026-09-15"})
    assert "certification_id=7" in body
    assert "2026-09-15" in body


def test_render_unknown_template_raises():
    with pytest.raises(KeyError):
        render("NOT_A_REAL_TEMPLATE", {})


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
