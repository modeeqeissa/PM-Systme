"""FastAPI app factory for notification-service.

Contract: notification-service/openapi.yaml. Notifications are created solely
by the Kafka consumer (app.events.consumer) and delivered by the background
delivery worker (app.services.delivery); a retention worker
(app.services.retention, FR-AUD-04) purges rows past the 90-day window. All
three spawn on startup unless disabled per env
(NOTIFICATION_{CONSUMER,DELIVERY,RETENTION}_ENABLED=0); tests drive them
explicitly.
"""
import contextlib

from fastapi import FastAPI

from app import config, db
from app.events import NotificationConsumer
from app.routers import notifications, preferences
from app.routers import settings as settings_router
from app.services import settings as settings_service
from app.services.delivery import DeliveryWorker
from app.services.retention import RetentionWorker

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the admin retention override from notification_settings into the
    # in-process cache the retention worker reads from.
    try:
        async with db.SessionLocal() as session:
            await settings_service.refresh(session)
    except Exception:  # pragma: no cover - DB not up yet in some test paths
        pass

    consumer: NotificationConsumer | None = None
    delivery: DeliveryWorker | None = None
    retention: RetentionWorker | None = None
    if config.consumer_enabled():
        consumer = NotificationConsumer(db.SessionLocal)
        await consumer.start()
        consumer.spawn()
    if config.delivery_enabled():
        delivery = DeliveryWorker(db.SessionLocal)
        delivery.spawn()
    if config.retention_enabled():
        retention = RetentionWorker(db.SessionLocal)
        retention.spawn()
    try:
        yield
    finally:
        if consumer is not None:
            await consumer.stop()
        if delivery is not None:
            await delivery.stop()
        if retention is not None:
            await retention.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Notification Service",
        version="1.0",
        description="Implements FR-NOTIF-01/02/03 (docs Section 4.8).",
        lifespan=lifespan,
    )

    app.include_router(notifications.router, prefix=API_PREFIX)
    app.include_router(preferences.router, prefix=API_PREFIX)
    app.include_router(settings_router.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "notification-service"}

    return app


app = create_app()
