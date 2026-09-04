"""FastAPI app factory for training-service.

Phase 1 STUB: health check only. The training_db schema (docs Section 9.3.5) is
migrated via Alembic but no domain endpoints exist yet. When the Phase 1 build
starts, register routers from app/routers/ below and (if the service publishes
or consumes events) add a lifespan like the built services.
"""
from fastapi import FastAPI

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Training & Certification Service",
        version="0.1-stub",
        description="Phase 1 stub — schema migrated, endpoints pending (FR section 4.5).",
    )

    # Phase 1: app.include_router(<resource>.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "training-service"}

    return app


app = create_app()
