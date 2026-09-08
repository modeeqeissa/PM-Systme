"""Runtime configuration for training-service.

Defaults target the local docker-compose Postgres (infra/docker-compose.yml).
Override with environment variables everywhere else; never commit a populated
.env (CLAUDE.md dev workflow).
"""
import os

_HOST = os.getenv("TRAINING_DB_HOST", "localhost")
_PORT = os.getenv("TRAINING_DB_PORT", "5432")
_NAME = os.getenv("TRAINING_DB_NAME", "training_db")
_USER = os.getenv("TRAINING_DB_USER", "pmp")
_PASSWORD = os.getenv("TRAINING_DB_PASSWORD", "pmp_dev_only")

_DSN = f"{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{_NAME}"


def async_database_url() -> str:
    return os.getenv("TRAINING_DATABASE_URL", f"postgresql+asyncpg://{_DSN}")


def sync_database_url() -> str:
    return os.getenv("TRAINING_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DSN}")


# --- Auth (iam-service integration) ---------------------------------------
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    """Expected `iss` claim — must match iam-service's IAM_JWT_ISSUER."""
    return os.getenv("TRAINING_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv(
        "TRAINING_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks"
    )


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("TRAINING_JWKS_CACHE_TTL", "300"))


# --- Course materials store (FR-TRAIN-01 / docs §9.3.5) -----------------
# Dev: a local directory of blobs keyed by an opaque file_ref, the same shape
# as evidence-service's vault (app/services/vault.py). Production: object
# storage behind the same store()/exists()/delete() interface. Materials are
# training documents, not chain-of-custody evidence, so no encryption here.
def materials_dir() -> str:
    return os.getenv(
        "TRAINING_MATERIALS_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".materials-store-dev"),
    )


# --- Expiry recompute (FR-TRAIN-03) ----------------------------------------
def expiry_lead_days() -> int:
    """A cert within this many days of expires_date becomes 'expiring_soon'."""
    return int(os.getenv("TRAINING_EXPIRY_LEAD_DAYS", "30"))


def recompute_enabled() -> bool:
    return os.getenv("TRAINING_RECOMPUTE_ENABLED", "1") not in ("0", "false", "False", "")


def recompute_poll_seconds() -> float:
    return float(os.getenv("TRAINING_RECOMPUTE_POLL_SECONDS", "3600"))
