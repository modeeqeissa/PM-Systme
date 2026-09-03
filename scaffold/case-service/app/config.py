"""Runtime configuration for case-service.

Values default to the local docker-compose Postgres (see infra/docker-compose.yml).
Override with environment variables in every other environment; never commit a
populated .env (CLAUDE.md dev workflow).
"""
import os

# Host-side credentials match infra/docker-compose.yml (dev only).
_DEFAULT_HOST = os.getenv("CASE_DB_HOST", "localhost")
_DEFAULT_PORT = os.getenv("CASE_DB_PORT", "5432")
_DEFAULT_USER = os.getenv("CASE_DB_USER", "pmp")
_DEFAULT_PASSWORD = os.getenv("CASE_DB_PASSWORD", "pmp_dev_only")
_DEFAULT_NAME = os.getenv("CASE_DB_NAME", "case_db")

_DEFAULT_DSN = (
    f"{_DEFAULT_USER}:{_DEFAULT_PASSWORD}@{_DEFAULT_HOST}:{_DEFAULT_PORT}/{_DEFAULT_NAME}"
)


def async_database_url() -> str:
    """SQLAlchemy async URL (asyncpg driver) used by the running service."""
    return os.getenv("CASE_DATABASE_URL", f"postgresql+asyncpg://{_DEFAULT_DSN}")


def sync_database_url() -> str:
    """SQLAlchemy sync URL (psycopg2 driver) used by Alembic migrations."""
    return os.getenv("CASE_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DEFAULT_DSN}")


# --- Auth (iam-service integration) ---------------------------------------
# Access tokens are RS256 JWTs issued by iam-service; their signature is verified
# against iam-service's JWKS (fetched from IAM and cached, see app/security/jwks.py).
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    """Expected `iss` claim — must match iam-service's IAM_JWT_ISSUER."""
    return os.getenv("CASE_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv(
        "CASE_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks"
    )


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("CASE_JWKS_CACHE_TTL", "300"))
