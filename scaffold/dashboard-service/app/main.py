"""FastAPI app factory for dashboard-service.

The HTTP surface is read-only (openapi.yaml / CLAUDE.md "no writes accepted").
Read models are maintained solely by the Kafka consumer
(app.events.consumer.DashboardConsumer), spawned on startup unless
DASHBOARD_CONSUMER_ENABLED=0 (tests drive it explicitly).
"""
import contextlib

from fastapi import FastAPI

from app import db
from app.config import consumer_enabled
from app.events import DashboardConsumer
from app.routers import dashboard

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    consumer: DashboardConsumer | None = None
    if consumer_enabled():
        consumer = DashboardConsumer(db.SessionLocal)
        await consumer.start()
        consumer.spawn()
    try:
        yield
    finally:
        if consumer is not None:
            await consumer.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Command Dashboard Service",
        version="1.0",
        description="CQRS read models (docs Section 9.3.7).",
        lifespan=lifespan,
    )
    app.include_router(dashboard.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "dashboard-service"}

    return app


app = create_app()
