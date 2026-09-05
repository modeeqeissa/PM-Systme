"""Test fixtures for integration-gateway-service.

* the service runs in-process (ASGITransport) against a dedicated
  ``integration_db_test`` database.
* iam-service runs as a **subprocess** on a free port against its own
  ``identity_db_integration_e2e`` database, so tests obtain real RS256
  access tokens through the genuine login -> MFA -> verify flow.

DB / auth env vars are set here *before* ``app`` is imported.
"""
import base64
import hashlib
import os
import pathlib
import socket
import subprocess
import time
import uuid

import httpx

_HERE = pathlib.Path(__file__).resolve().parent
_SCAFFOLD = _HERE.parents[1]
_IAM_DIR = _SCAFFOLD / "iam-service"
_IAM_PY = _IAM_DIR / ".venv" / "bin" / "python"

_PG = {
    "host": os.getenv("INTEGRATION_GATEWAY_DB_HOST", "localhost"),
    "port": os.getenv("INTEGRATION_GATEWAY_DB_PORT", "5432"),
    "user": os.getenv("INTEGRATION_GATEWAY_DB_USER", "pmp"),
    "password": os.getenv("INTEGRATION_GATEWAY_DB_PASSWORD", "pmp_dev_only"),
}
TEST_DB = "integration_db_test"
_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{TEST_DB}"

os.environ["INTEGRATION_GATEWAY_DATABASE_URL"] = f"postgresql+asyncpg://{_DSN}"
os.environ["INTEGRATION_GATEWAY_DATABASE_URL_SYNC"] = f"postgresql+psycopg2://{_DSN}"

_IAM_DB = "identity_db_integration_e2e"
_IAM_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{_IAM_DB}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IAM_PORT = int(os.getenv("INTEGRATION_TEST_IAM_PORT", str(_free_port())))
_IAM_BASE = f"http://127.0.0.1:{_IAM_PORT}"

_IAM_JWT_PEM = str(_HERE / ".e2e-iam-jwt-private.pem")
_IAM_ENV = {
    **os.environ,
    "IAM_DATABASE_URL": f"postgresql+asyncpg://{_IAM_DSN}",
    "IAM_DATABASE_URL_SYNC": f"postgresql+psycopg2://{_IAM_DSN}",
    "IAM_JWT_PRIVATE_KEY_PATH": _IAM_JWT_PEM,
    "IAM_JWT_ISSUER": "pmp-iam-service",
    "IAM_MFA_ENC_KEY": base64.urlsafe_b64encode(
        hashlib.sha256(b"integration-e2e-mfa-key").digest()
    ).decode(),
    "IAM_ACCESS_TOKEN_TTL": "900",
}

os.environ["INTEGRATION_GATEWAY_IAM_JWKS_URL"] = f"{_IAM_BASE}/api/v1/auth/jwks"
os.environ["INTEGRATION_GATEWAY_JWT_ISSUER"] = "pmp-iam-service"

os.environ["EVENTS_RELAY_ENABLED"] = "0"
os.environ.setdefault("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")
os.environ["EVENTS_TOPIC_PREFIX"] = f"intgt_{uuid.uuid4().hex[:8]}."

import psycopg2  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.db as _db  # noqa: E402

engine = create_async_engine(
    os.environ["INTEGRATION_GATEWAY_DATABASE_URL"], poolclass=NullPool
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db.engine = engine
_db.SessionLocal = SessionLocal

from app.events import OutboxRelay, topic_for  # noqa: E402
from app.main import app  # noqa: E402

# "ICT Admin" holds integration.read/write (migration 0007); "Auditor" holds
# neither.
_E2E_USERS = {"E2E-ICT": "ICT Admin", "E2E-NONE": "Auditor"}
_E2E_PASSWORD = "E2e!TestPassw0rd"
_totp_secrets: dict[str, str] = {}


def _recreate_database(name: str) -> None:
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


def _wait_for_http(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError as exc:
            last = exc
        time.sleep(0.3)
    raise RuntimeError(f"iam-service did not become ready at {url}: {last}")


def _iam_enroll_mfa(badge: str) -> None:
    with httpx.Client(base_url=_IAM_BASE, timeout=10.0) as c:
        login = c.post(
            "/api/v1/auth/login",
            json={"badge_number": badge, "password": _E2E_PASSWORD},
        )
        login.raise_for_status()
        enroll = c.post(
            "/api/v1/auth/mfa/enroll",
            headers={"Authorization": f"Bearer {login.json()['mfa_token']}"},
        )
        enroll.raise_for_status()
        _totp_secrets[badge] = enroll.json()["secret"]


def iam_access_token(badge: str) -> str:
    import pyotp

    with httpx.Client(base_url=_IAM_BASE, timeout=10.0) as c:
        login = c.post(
            "/api/v1/auth/login",
            json={"badge_number": badge, "password": _E2E_PASSWORD},
        )
        login.raise_for_status()
        verify = c.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": login.json()["mfa_token"],
                "code": pyotp.TOTP(_totp_secrets[badge]).now(),
            },
        )
        verify.raise_for_status()
        return verify.json()["access_token"]


@pytest.fixture(scope="session", autouse=True)
def _integration_database():
    _recreate_database(TEST_DB)
    cfg = Config(str(_HERE.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(_HERE.parent / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session", autouse=True)
def iam_server():
    if not _IAM_PY.exists():
        pytest.skip(f"iam-service venv not found at {_IAM_PY}")

    _recreate_database(_IAM_DB)
    subprocess.run(
        [str(_IAM_PY), "-m", "alembic", "upgrade", "head"],
        cwd=_IAM_DIR, env=_IAM_ENV, check=True, capture_output=True,
    )
    for badge, role in _E2E_USERS.items():
        subprocess.run(
            [
                str(_IAM_PY), "-m", "scripts.create_user",
                "--badge", badge, "--password", _E2E_PASSWORD,
                "--name", badge, "--roles", role,
            ],
            cwd=_IAM_DIR, env=_IAM_ENV, check=True, capture_output=True,
        )

    proc = subprocess.Popen(
        [
            str(_IAM_PY), "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(_IAM_PORT), "--log-level", "warning",
        ],
        cwd=_IAM_DIR, env=_IAM_ENV,
    )
    try:
        _wait_for_http(f"{_IAM_BASE}/health")
        for badge in _E2E_USERS:
            _iam_enroll_mfa(badge)
        yield _IAM_BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def token_ict(iam_server) -> str:
    return iam_access_token("E2E-ICT")


@pytest.fixture(scope="session")
def token_none(iam_server) -> str:
    return iam_access_token("E2E-NONE")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_ict(token_ict) -> dict:
    return bearer(token_ict)


@pytest.fixture
def auth_none(token_none) -> dict:
    return bearer(token_none)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE external_system_logs, outbox_events RESTART IDENTITY CASCADE")
        )
        # restore the four seeded configs to enabled=true between tests
        await conn.execute(text("UPDATE integration_configs SET enabled = true"))
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def outbox_relay():
    relay = OutboxRelay(SessionLocal)
    await relay.start()
    try:
        yield relay
    finally:
        await relay.stop()


@pytest.fixture
def read_kafka():
    import asyncio
    import json

    from aiokafka import AIOKafkaConsumer

    async def _read(event_type: str, expected: int = 1, timeout: float = 10.0):
        topic = topic_for(event_type)
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=os.environ["EVENTS_KAFKA_BOOTSTRAP"],
            group_id=f"test-{uuid.uuid4().hex}",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await consumer.start()
        out: list[dict] = []
        try:
            deadline = asyncio.get_event_loop().time() + timeout
            while len(out) < expected and asyncio.get_event_loop().time() < deadline:
                batch = await consumer.getmany(timeout_ms=1000)
                for _tp, msgs in batch.items():
                    for m in msgs:
                        out.append(json.loads(m.value))
        finally:
            await consumer.stop()
        return out

    return _read
