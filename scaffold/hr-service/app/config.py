"""Runtime configuration for hr-service.

Defaults target the local docker-compose Postgres (infra/docker-compose.yml).
Override with environment variables everywhere else; never commit a populated
.env (CLAUDE.md dev workflow).
"""
import os

_HOST = os.getenv("HR_DB_HOST", "localhost")
_PORT = os.getenv("HR_DB_PORT", "5432")
_NAME = os.getenv("HR_DB_NAME", "hr_db")
_USER = os.getenv("HR_DB_USER", "pmp")
_PASSWORD = os.getenv("HR_DB_PASSWORD", "pmp_dev_only")

_DSN = f"{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{_NAME}"


def async_database_url() -> str:
    return os.getenv("HR_DATABASE_URL", f"postgresql+asyncpg://{_DSN}")


def sync_database_url() -> str:
    return os.getenv("HR_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DSN}")


# --- Auth (iam-service integration) ---------------------------------------
# Access tokens are RS256 JWTs issued by iam-service; their signature is verified
# against iam-service's JWKS (fetched from IAM and cached, see app/security/jwks.py).
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    """Expected `iss` claim — must match iam-service's IAM_JWT_ISSUER."""
    return os.getenv("HR_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv("HR_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks")


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("HR_JWKS_CACHE_TTL", "300"))
