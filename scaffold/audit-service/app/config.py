"""Runtime configuration for audit-service.

Two DB identities (docs Section 9.3.10):
* the application connects as ``audit_service_app`` - INSERT/SELECT only on
  audit_logs; UPDATE/DELETE revoked so history cannot be altered;
* Alembic migrations connect as the owner (``pmp`` in local dev).
"""
import os

_HOST = os.getenv("AUDIT_DB_HOST", "localhost")
_PORT = os.getenv("AUDIT_DB_PORT", "5432")
_NAME = os.getenv("AUDIT_DB_NAME", "audit_db")

_APP_USER = os.getenv("AUDIT_DB_APP_USER", "audit_service_app")
_APP_PASSWORD = os.getenv("AUDIT_DB_APP_PASSWORD", "audit_app_dev_only")
_OWNER_USER = os.getenv("AUDIT_DB_OWNER_USER", "pmp")
_OWNER_PASSWORD = os.getenv("AUDIT_DB_OWNER_PASSWORD", "pmp_dev_only")

APP_DB_ROLE = _APP_USER


def async_database_url() -> str:
    return os.getenv(
        "AUDIT_DATABASE_URL",
        f"postgresql+asyncpg://{_APP_USER}:{_APP_PASSWORD}@{_HOST}:{_PORT}/{_NAME}",
    )


def sync_database_url() -> str:
    return os.getenv(
        "AUDIT_DATABASE_URL_SYNC",
        f"postgresql+psycopg2://{_OWNER_USER}:{_OWNER_PASSWORD}@{_HOST}:{_PORT}/{_NAME}",
    )


# --- Auth (iam-service) --------------------------------------------------
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    return os.getenv("AUDIT_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv("AUDIT_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks")


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("AUDIT_JWKS_CACHE_TTL", "300"))


# --- Kafka consumer ---------------------------------------------------------
def kafka_bootstrap() -> str:
    return os.getenv("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")


def topic_prefix() -> str:
    return os.getenv("EVENTS_TOPIC_PREFIX", "")


def consumer_group() -> str:
    return os.getenv("AUDIT_CONSUMER_GROUP", "audit-service")


def consumer_enabled() -> bool:
    return os.getenv("AUDIT_CONSUMER_ENABLED", "1") not in ("0", "false", "False", "")


# --- Retention (FR-AUD-04) ------------------------------------------------
# Advisory only: audit-service has no delete path. Purge/archival beyond this
# window is a separate privileged job, not the application.
RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "3650"))  # ~10 years
