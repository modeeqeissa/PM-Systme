"""FastAPI app factory for audit-service.

The HTTP surface is read-only (openapi.yaml). Audit entries are written solely by
the Kafka consumer (app.events.consumer), spawned on startup unless
AUDIT_CONSUMER_ENABLED=0 (tests drive the consumer explicitly).
"""
import contextlib

from fastapi import FastAPI

from app import db
from app.config import consumer_enabled
from app.events import AuditConsumer
from app.routers import audit

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    consumer: AuditConsumer | None = None
    if consumer_enabled():
        consumer = AuditConsumer(db.SessionLocal)
        await consumer.start()
        consumer.spawn()
    try:
        yield
    finally:
        if consumer is not None:
            await consumer.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Audit Log Service",
        version="1.0",
        description="Implements FR-AUD-01..04 (docs Section 4.10).",
        lifespan=lifespan,
    )
    app.include_router(audit.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "audit-service"}

    return app


app = create_app()
