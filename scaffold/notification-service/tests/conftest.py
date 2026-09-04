"""Minimal fixtures for the notification-service stub: a fresh migrated notification_db_test + ASGI client."""
import os
import pathlib

_HERE = pathlib.Path(__file__).resolve().parent
_PG = {"host": "localhost", "port": "5432", "user": "pmp", "password": "pmp_dev_only"}
TEST_DB = "notification_db_test"
_DSN = f"pmp:pmp_dev_only@localhost:5432/{TEST_DB}"

os.environ["NOTIFICATION_DATABASE_URL"] = f"postgresql+asyncpg://{_DSN}"
os.environ["NOTIFICATION_DATABASE_URL_SYNC"] = f"postgresql+psycopg2://{_DSN}"

import psycopg2  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


def _recreate(name: str) -> None:
    conn = psycopg2.connect(dbname="postgres", **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
            cur.execute(f'CREATE DATABASE "{name}"')
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _database():
    _recreate(TEST_DB)
    cfg = Config(str(_HERE.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(_HERE.parent / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
