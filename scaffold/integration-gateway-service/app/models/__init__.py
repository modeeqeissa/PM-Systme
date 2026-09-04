"""ORM for integration_db (docs Section 9.3.9 / migration 0001). Phase 1 stub."""
from app.models.base import Base
from app.models.integration import ExternalSystemLog, IntegrationConfig

__all__ = ["Base", "IntegrationConfig", "ExternalSystemLog"]
