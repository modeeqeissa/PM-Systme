"""Runtime configuration for evidence-service.

Two DB identities on purpose (docs Section 9.3.3):

* the **application** connects as ``evidence_service_app`` - a least-privilege
  role with INSERT/SELECT (no UPDATE/DELETE) on custody_events, so append-only
  is enforced by the database, not just the code;
* **Alembic migrations** connect as the owner (``pmp`` in local dev) because
  they need DDL rights.

Override everything with env vars outside local dev; never commit a populated
.env (CLAUDE.md dev workflow).
"""
import os

_HOST = os.getenv("EVIDENCE_DB_HOST", "localhost")
_PORT = os.getenv("EVIDENCE_DB_PORT", "5432")
_NAME = os.getenv("EVIDENCE_DB_NAME", "evidence_db")

# Least-privilege application role (created by migration 0001).
_APP_USER = os.getenv("EVIDENCE_DB_APP_USER", "evidence_service_app")
_APP_PASSWORD = os.getenv("EVIDENCE_DB_APP_PASSWORD", "evidence_app_dev_only")

# Owner / migration role.
_OWNER_USER = os.getenv("EVIDENCE_DB_OWNER_USER", "pmp")
_OWNER_PASSWORD = os.getenv("EVIDENCE_DB_OWNER_PASSWORD", "pmp_dev_only")

APP_DB_ROLE = _APP_USER  # exported so the migration knows which role to lock down


def async_database_url() -> str:
    """URL the running service uses - the least-privilege application role."""
    return os.getenv(
        "EVIDENCE_DATABASE_URL",
        f"postgresql+asyncpg://{_APP_USER}:{_APP_PASSWORD}@{_HOST}:{_PORT}/{_NAME}",
    )


def sync_database_url() -> str:
    """URL Alembic uses - the owner role (needs DDL)."""
    return os.getenv(
        "EVIDENCE_DATABASE_URL_SYNC",
        f"postgresql+psycopg2://{_OWNER_USER}:{_OWNER_PASSWORD}@{_HOST}:{_PORT}/{_NAME}",
    )


# --- Auth (iam-service integration) ---------------------------------------
JWT_ALG = "RS256"


def jwt_issuer() -> str:
    return os.getenv("EVIDENCE_JWT_ISSUER", "pmp-iam-service")


def iam_jwks_url() -> str:
    return os.getenv(
        "EVIDENCE_IAM_JWKS_URL", "http://localhost:8001/api/v1/auth/jwks"
    )


def jwks_cache_ttl_seconds() -> int:
    return int(os.getenv("EVIDENCE_JWKS_CACHE_TTL", "300"))


# --- Encrypted evidence vault (FR-EVID-05) ------------------------------
# Dev: a local directory of Fernet-encrypted blobs. Production: an object-store
# backed vault with envelope encryption / KMS - same interface (app/services/vault.py).
def vault_dir() -> str:
    return os.getenv(
        "EVIDENCE_VAULT_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".evidence-vault-dev"),
    )


VAULT_ENC_KEY = os.getenv("EVIDENCE_VAULT_KEY")  # urlsafe-base64 32-byte Fernet key
