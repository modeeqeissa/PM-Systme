"""FastAPI app factory + router registration for training-service.

Contract: training-service/openapi.yaml. The OpenAPI `servers` entry is
`/api/v1`, so every documented path is mounted under that prefix here.

On startup an outbox relay (app.events.relay) publishes domain events to
Kafka and a recompute task (app.services.recompute_task) periodically flags
expiring/expired certifications (FR-TRAIN-03); disable either with
EVENTS_RELAY_ENABLED=0 / TRAINING_RECOMPUTE_ENABLED=0 (tests drive both
explicitly instead).
"""
import contextlib

from fastapi import FastAPI

from app import config, db
from app.events import OutboxRelay
from app.events.config import relay_enabled
from app.routers import certifications, courses, officer_certifications
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
        title="PMP Training & Certification Service",
        version="1.0",
        description="Implements FR-TRAIN-01..03 (docs Section 4.5).",
        lifespan=lifespan,
    )

    app.include_router(courses.router, prefix=API_PREFIX)
    app.include_router(certifications.router, prefix=API_PREFIX)
    app.include_router(officer_certifications.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "training-service"}

    return app


app = create_app()
