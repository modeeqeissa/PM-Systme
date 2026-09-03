"""FastAPI app factory + router registration for evidence-service.

Contract: evidence-service/openapi.yaml. The OpenAPI `servers` entry is `/api/v1`,
so every documented path is mounted under that prefix here.

On startup an outbox relay (app.events.relay) is spawned to publish domain
events to Kafka; disable it with EVENTS_RELAY_ENABLED=0 (tests drive the relay
explicitly).
"""
import contextlib

from fastapi import FastAPI

from app import db
from app.events import OutboxRelay
from app.events.config import relay_enabled
from app.routers import custody, evidence

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
        title="PMP Evidence & Chain-of-Custody Service",
        version="1.0",
        description="Implements FR-EVID-01..07 (docs Section 4.3).",
        lifespan=lifespan,
    )

    app.include_router(evidence.router, prefix=API_PREFIX)
    app.include_router(custody.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "evidence-service"}

    return app


app = create_app()
