"""Runtime configuration for dashboard-service.

dashboard_db holds only CQRS read models rebuilt from domain events, so the
service connects with a single role (owner in local dev) for both migrations and
runtime. No append-only enforcement: the projections are disposable and can be
rebuilt by replaying Kafka.
"""
import os

_HOST = os.getenv("DASHBOARD_DB_HOST", "localhost")
_PORT = os.getenv("DASHBOARD_DB_PORT", "5432")
_NAME = os.getenv("DASHBOARD_DB_NAME", "dashboard_db")
_USER = os.getenv("DASHBOARD_DB_USER", "pmp")
_PASSWORD = os.getenv("DASHBOARD_DB_PASSWORD", "pmp_dev_only")

_DSN = f"{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{_NAME}"


def async_database_url() -> str:
    return os.getenv("DASHBOARD_DATABASE_URL", f"postgresql+asyncpg://{_DSN}")


def sync_database_url() -> str:
    return os.getenv("DASHBOARD_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DSN}")


# --- Auth (iam-service) --------------------------------------------------
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    return os.getenv("DASHBOARD_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv("DASHBOARD_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks")


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("DASHBOARD_JWKS_CACHE_TTL", "300"))


# --- Kafka consumer ---------------------------------------------------------
def kafka_bootstrap() -> str:
    return os.getenv("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")


def topic_prefix() -> str:
    return os.getenv("EVENTS_TOPIC_PREFIX", "")


def consumer_group() -> str:
    return os.getenv("DASHBOARD_CONSUMER_GROUP", "dashboard-service")


def consumer_enabled() -> bool:
    return os.getenv("DASHBOARD_CONSUMER_ENABLED", "1") not in ("0", "false", "False", "")


NIL_UUID = "00000000-0000-0000-0000-000000000000"
