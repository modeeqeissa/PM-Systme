"""Runtime configuration for integration-gateway-service.

Defaults target the local docker-compose Postgres (infra/docker-compose.yml).
Override with environment variables everywhere else; never commit a populated
.env (CLAUDE.md dev workflow).
"""
import os

_HOST = os.getenv("INTEGRATION_GATEWAY_DB_HOST", "localhost")
_PORT = os.getenv("INTEGRATION_GATEWAY_DB_PORT", "5432")
_NAME = os.getenv("INTEGRATION_GATEWAY_DB_NAME", "integration_db")
_USER = os.getenv("INTEGRATION_GATEWAY_DB_USER", "pmp")
_PASSWORD = os.getenv("INTEGRATION_GATEWAY_DB_PASSWORD", "pmp_dev_only")

_DSN = f"{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{_NAME}"


def async_database_url() -> str:
    return os.getenv("INTEGRATION_GATEWAY_DATABASE_URL", f"postgresql+asyncpg://{_DSN}")


def sync_database_url() -> str:
    return os.getenv("INTEGRATION_GATEWAY_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DSN}")


# --- Auth (iam-service integration) ---------------------------------------
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    """Expected `iss` claim — must match iam-service's IAM_JWT_ISSUER."""
    return os.getenv("INTEGRATION_GATEWAY_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv(
        "INTEGRATION_GATEWAY_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks"
    )


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("INTEGRATION_GATEWAY_JWKS_CACHE_TTL", "300"))


# --- Retention / purge (FR-AUD-04 / docs §9.6) ------------------------------
# external_system_logs are 180-day operational data — safe to actually delete.
# The purge job (app.services.retention) runs in-process; period configurable
# by the ICT unit.
def retention_enabled() -> bool:
    return os.getenv("INTEGRATION_GATEWAY_RETENTION_ENABLED", "1") not in (
        "0", "false", "False", "",
    )


def log_retention_days() -> int:
    return int(os.getenv("INTEGRATION_GATEWAY_LOG_RETENTION_DAYS", "180"))


def retention_poll_seconds() -> float:
    return float(os.getenv("INTEGRATION_GATEWAY_RETENTION_POLL_SECONDS", "86400"))
