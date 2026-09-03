"""Runtime configuration for iam-service.

Defaults target the local docker-compose Postgres (infra/docker-compose.yml).
Override with environment variables everywhere else; never commit a populated
.env (CLAUDE.md dev workflow).
"""
import os

_DEFAULT_HOST = os.getenv("IAM_DB_HOST", "localhost")
_DEFAULT_PORT = os.getenv("IAM_DB_PORT", "5432")
_DEFAULT_USER = os.getenv("IAM_DB_USER", "pmp")
_DEFAULT_PASSWORD = os.getenv("IAM_DB_PASSWORD", "pmp_dev_only")
_DEFAULT_NAME = os.getenv("IAM_DB_NAME", "identity_db")

_DEFAULT_DSN = (
    f"{_DEFAULT_USER}:{_DEFAULT_PASSWORD}@{_DEFAULT_HOST}:{_DEFAULT_PORT}/{_DEFAULT_NAME}"
)


def async_database_url() -> str:
    return os.getenv("IAM_DATABASE_URL", f"postgresql+asyncpg://{_DEFAULT_DSN}")


def sync_database_url() -> str:
    return os.getenv("IAM_DATABASE_URL_SYNC", f"postgresql+psycopg2://{_DEFAULT_DSN}")


# --- Tokens -----------------------------------------------------------------
# RS256 so other services verify via the public JWKS without calling iam-service
# (FR-IAM-08). In dev a keypair is generated on first use and cached to disk;
# set IAM_JWT_PRIVATE_KEY (PEM) in every real environment.
JWT_ALG = "RS256"
JWT_ISSUER = os.getenv("IAM_JWT_ISSUER", "pmp-iam-service")
JWT_KID = os.getenv("IAM_JWT_KID", "iam-dev-1")
JWT_PRIVATE_KEY_PEM = os.getenv("IAM_JWT_PRIVATE_KEY")
JWT_PRIVATE_KEY_PATH = os.getenv(
    "IAM_JWT_PRIVATE_KEY_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), ".dev-jwt-private.pem"),
)

ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("IAM_ACCESS_TOKEN_TTL", "900"))  # <= 15 min
REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("IAM_REFRESH_TOKEN_TTL", str(7 * 24 * 3600)))
MFA_TOKEN_TTL_SECONDS = int(os.getenv("IAM_MFA_TOKEN_TTL", "300"))

# --- MFA -------------------------------------------------------------------
# The TOTP secret is stored encrypted at rest (SRS 9.3.1). Dev uses a static
# Fernet key; real deployments use envelope encryption backed by a KMS.
MFA_ENC_KEY = os.getenv("IAM_MFA_ENC_KEY")  # urlsafe-base64 32-byte Fernet key
MFA_ISSUER_LABEL = os.getenv("IAM_MFA_ISSUER_LABEL", "PMP")

# --- Account / password policy (FR-IAM-05, FR-IAM-07) --------------------
MAX_FAILED_LOGINS = int(os.getenv("IAM_MAX_FAILED_LOGINS", "5"))
PASSWORD_MIN_LENGTH = int(os.getenv("IAM_PASSWORD_MIN_LENGTH", "12"))
