"""FastAPI app factory for notification-service.

Contract: notification-service/openapi.yaml. Notifications are created solely
by the Kafka consumer (app.events.consumer) and delivered by the background
delivery worker (app.services.delivery); both are spawned on startup unless
NOTIFICATION_CONSUMER_ENABLED=0 / NOTIFICATION_DELIVERY_ENABLED=0 (tests
drive them explicitly).
"""
import contextlib

from fastapi import FastAPI

from app import config, db
from app.events import NotificationConsumer
from app.routers import notifications
from app.services.delivery import DeliveryWorker

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    consumer: NotificationConsumer | None = None
    delivery: DeliveryWorker | None = None
    if config.consumer_enabled():
        consumer = NotificationConsumer(db.SessionLocal)
        await consumer.start()
        consumer.spawn()
    if config.delivery_enabled():
        delivery = DeliveryWorker(db.SessionLocal)
        delivery.spawn()
    try:
        yield
    finally:
        if consumer is not None:
            await consumer.stop()
        if delivery is not None:
            await delivery.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Notification Service",
        version="1.0",
        description="Implements FR-NOTIF-01/03 (docs Section 4.8). FR-NOTIF-02 "
        "(channel preferences) is deferred — no supporting table in SRS §9.3.8.",
        lifespan=lifespan,
    )

    app.include_router(notifications.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "notification-service"}

    return app


app = create_app()
