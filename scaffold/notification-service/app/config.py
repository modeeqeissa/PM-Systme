"""Runtime configuration for notification-service.

Defaults target the local docker-compose Postgres (infra/docker-compose.yml).
Override with environment variables everywhere else; never commit a populated
.env (CLAUDE.md dev workflow).
"""
import os

_HOST = os.getenv("NOTIFICATION_DB_HOST", "localhost")
_PORT = os.getenv("NOTIFICATION_DB_PORT", "5432")
_NAME = os.getenv("NOTIFICATION_DB_NAME", "notification_db")
_USER = os.getenv("NOTIFICATION_DB_USER", "pmp")
_PASSWORD = os.getenv("NOTIFICATION_DB_PASSWORD", "pmp_dev_only")

_DSN = f"{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{_NAME}"


def async_database_url() -> str:
    return os.getenv("NOTIFICATION_DATABASE_URL", f"postgresql+asyncpg://{_DSN}")


def sync_database_url() -> str:
    return os.getenv("NOTIFICATION_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DSN}")


# --- Auth (iam-service) ------------------------------------------------------
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    return os.getenv("NOTIFICATION_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv(
        "NOTIFICATION_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks"
    )


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("NOTIFICATION_JWKS_CACHE_TTL", "300"))


# --- Kafka consumer ----------------------------------------------------------
def kafka_bootstrap() -> str:
    return os.getenv("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")


def topic_prefix() -> str:
    return os.getenv("EVENTS_TOPIC_PREFIX", "")


def consumer_group() -> str:
    return os.getenv("NOTIFICATION_CONSUMER_GROUP", "notification-service")


def consumer_enabled() -> bool:
    return os.getenv("NOTIFICATION_CONSUMER_ENABLED", "1") not in ("0", "false", "False", "")


# --- Delivery worker (TD-004: dev channel only, see TODO.md) -----------------
def delivery_enabled() -> bool:
    return os.getenv("NOTIFICATION_DELIVERY_ENABLED", "1") not in ("0", "false", "False", "")


def delivery_poll_seconds() -> float:
    return float(os.getenv("NOTIFICATION_DELIVERY_POLL_SECONDS", "5.0"))
