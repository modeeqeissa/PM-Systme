"""FastAPI app factory + router registration for iam-service.

Contract: iam-service/openapi.yaml. The OpenAPI `servers` entry is `/api/v1`,
so every documented path is mounted under that prefix here.
"""
from fastapi import FastAPI

from app.routers import auth, roles, users

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMP Identity & Access Management Service",
        version="1.0",
        description="Implements FR-IAM-01..08 (docs Section 4.1).",
    )

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(roles.router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "iam-service"}

    return app


app = create_app()
