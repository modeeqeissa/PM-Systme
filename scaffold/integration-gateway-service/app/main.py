"""FastAPI app factory + router registration for integration-gateway-service.

Contract: integration-gateway-service/openapi.yaml. The OpenAPI `servers`
entry is `/api/v1`, so every documented path is mounted under that prefix
here.

On startup an outbox relay (app.events.relay) publishes domain events to
Kafka; disable with EVENTS_RELAY_ENABLED=0 (tests drive the relay
explicitly). CorrelationIdMiddleware runs on every request (FR-INT-05).
"""
import contextlib

from fastapi import FastAPI

from app import db
from app.events import OutboxRelay
from app.events.config import relay_enabled
from app.routers import adapters, external_system_logs, integration_configs
from app.services.correlation import CorrelationIdMiddleware

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    relay: OutboxRelay | None = None
    if relay_enabled():
        relay = OutboxRelay(db.SessionLocal)
        await relay.start()
        relay.spawn()
    try:
        yield
    finally:
        if relay is not None:
            await relay.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Integration Gateway Service",
        version="1.0",
        description="Implements FR-INT-01..05 (docs Section 4.9) as a stub framework "
        "— no real external system to integrate with yet. See TODO.md TD-005.",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(integration_configs.router, prefix=API_PREFIX)
    app.include_router(external_system_logs.router, prefix=API_PREFIX)
    app.include_router(adapters.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "integration-gateway-service"}

    return app


app = create_app()
