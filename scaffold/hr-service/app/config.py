"""Runtime configuration for hr-service (Phase 1 stub).

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
