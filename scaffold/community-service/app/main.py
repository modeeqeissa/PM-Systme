"""FastAPI app factory + router registration for community-service.

Contract: community-service/openapi.yaml. The OpenAPI `servers` entry is
`/api/v1`, so every documented path is mounted under that prefix here.

On startup an outbox relay (app.events.relay) publishes domain events to
Kafka and a recompute task (app.services.recompute_task) periodically flags
overdue follow-up actions (FR-COMM-04); disable either with
EVENTS_RELAY_ENABLED=0 / COMMUNITY_RECOMPUTE_ENABLED=0 (tests drive both
explicitly instead).
"""
import contextlib

from fastapi import FastAPI

from app import config, db
from app.events import OutboxRelay
from app.events.config import relay_enabled
from app.routers import concerns, follow_up_actions, meetings
from app.services.recompute_task import RecomputeTask

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    relay: OutboxRelay | None = None
    recompute: RecomputeTask | None = None
    if relay_enabled():
        relay = OutboxRelay(db.SessionLocal)
        await relay.start()
        relay.spawn()
    if config.recompute_enabled():
        recompute = RecomputeTask(db.SessionLocal)
        recompute.spawn()
    try:
        yield
    finally:
        if relay is not None:
            await relay.stop()
        if recompute is not None:
            await recompute.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Community Policing Service",
        version="1.0",
        description="Implements FR-COMM-01..04 (docs Section 4.4).",
        lifespan=lifespan,
    )

    app.include_router(meetings.router, prefix=API_PREFIX)
    app.include_router(concerns.router, prefix=API_PREFIX)
    app.include_router(follow_up_actions.by_concern_router, prefix=API_PREFIX)
    app.include_router(follow_up_actions.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "community-service"}

    return app


app = create_app()
