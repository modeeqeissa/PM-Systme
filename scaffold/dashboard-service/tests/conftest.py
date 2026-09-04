"""Test fixtures for dashboard-service.

* dashboard-service runs in-process (ASGITransport) against ``dashboard_db_test``.
* iam-service runs as a subprocess for real ``dashboard.view`` tokens.
* A real Kafka broker (infra) is used with a per-test topic prefix; tests publish
  event envelopes and drive DashboardConsumer.process_available() explicitly.
"""
import base64
import datetime as dt
import hashlib
import json
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

_PG = {"host": "localhost", "port": "5432", "user": "pmp", "password": "pmp_dev_only"}
_TEST_DB = "dashboard_db_test"
_ASYNC = f"postgresql+asyncpg://pmp:pmp_dev_only@localhost:5432/{_TEST_DB}"
_SYNC = f"postgresql+psycopg2://pmp:pmp_dev_only@localhost:5432/{_TEST_DB}"

os.environ["DASHBOARD_DATABASE_URL"] = _ASYNC
os.environ["DASHBOARD_DATABASE_URL_SYNC"] = _SYNC
os.environ["DASHBOARD_CONSUMER_ENABLED"] = "0"
os.environ.setdefault("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")
os.environ["EVENTS_TOPIC_PREFIX"] = f"dsh_{uuid.uuid4().hex[:8]}."

_IAM_DB = "identity_db_dash_e2e"
_IAM_DSN = f"pmp:pmp_dev_only@localhost:5432/{_IAM_DB}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IAM_PORT = int(os.getenv("DASHBOARD_TEST_IAM_PORT", str(_free_port())))
_IAM_BASE = f"http://127.0.0.1:{_IAM_PORT}"
_IAM_ENV = {
    **os.environ,
    "IAM_DATABASE_URL": f"postgresql+asyncpg://{_IAM_DSN}",
    "IAM_DATABASE_URL_SYNC": f"postgresql+psycopg2://{_IAM_DSN}",
    "IAM_JWT_PRIVATE_KEY_PATH": str(_HERE / ".e2e-iam-jwt-private.pem"),
    "IAM_JWT_ISSUER": "pmp-iam-service",
    "IAM_MFA_ENC_KEY": base64.urlsafe_b64encode(
        hashlib.sha256(b"dash-e2e-mfa-key").digest()
    ).decode(),
    "IAM_ACCESS_TOKEN_TTL": "900",
}
os.environ["DASHBOARD_IAM_JWKS_URL"] = f"{_IAM_BASE}/api/v1/auth/jwks"
os.environ["DASHBOARD_JWT_ISSUER"] = "pmp-iam-service"

import psycopg2  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from aiokafka import AIOKafkaProducer  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.db as _db  # noqa: E402

engine = create_async_engine(_ASYNC, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db.engine = engine
_db.SessionLocal = SessionLocal

from app.events import DashboardConsumer  # noqa: E402
from app.events.topics import consumed_topics  # noqa: E402
from app.main import app  # noqa: E402

# Auditor holds dashboard.view; Patrol Officer does not (iam seed 0002).
_USERS = {"DASH-VIEW": "Auditor", "DASH-NONE": "Patrol Officer"}
_PASSWORD = "Dash!Testpw1234"
_totp_secrets: dict[str, str] = {}

_BASE_TOPIC = {
    "CaseOpened": "case.opened",
    "CaseStatusChanged": "case.status_changed",
    "ArrestRecorded": "case.arrest_recorded",
    "EvidenceLogged": "evidence.logged",
    "CustodyEventRecorded": "evidence.custody_recorded",
    "EvidenceHashMismatch": "evidence.hash_mismatch",
}


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
    raise RuntimeError(f"iam-service not ready at {url}: {last}")


def _iam_enroll(badge: str) -> None:
    with httpx.Client(base_url=_IAM_BASE, timeout=10.0) as c:
        login = c.post(
            "/api/v1/auth/login", json={"badge_number": badge, "password": _PASSWORD}
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
            "/api/v1/auth/login", json={"badge_number": badge, "password": _PASSWORD}
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


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_envelope(event_type: str, payload: dict, **over) -> dict:
    env = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": over.get(
            "occurred_at", dt.datetime.now(dt.timezone.utc).isoformat()
        ),
        "aggregate_type": "x",
        "aggregate_id": str(uuid.uuid4()),
        "actor_id": over.get("actor_id", str(uuid.uuid4())),
        "actor_role": over.get("actor_role", "Investigator"),
        "service": over.get("service", "case-service"),
        "payload": payload,
    }
    return env


@pytest.fixture(scope="session", autouse=True)
def _dashboard_database():
    _recreate_database(_TEST_DB)
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
    for badge, role in _USERS.items():
        subprocess.run(
            [
                str(_IAM_PY), "-m", "scripts.create_user",
                "--badge", badge, "--password", _PASSWORD, "--name", badge,
                "--roles", role,
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
        for badge in _USERS:
            _iam_enroll(badge)
        yield _IAM_BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def token_view(iam_server) -> str:
    return iam_access_token("DASH-VIEW")


@pytest.fixture(scope="session")
def token_none(iam_server) -> str:
    return iam_access_token("DASH-NONE")


@pytest.fixture
def auth_view(token_view) -> dict:
    return bearer(token_view)


@pytest.fixture
def auth_none(token_none) -> dict:
    return bearer(token_none)


@pytest.fixture(autouse=True)
def _topic_prefix():
    prefix = f"dsh_{uuid.uuid4().hex}."
    os.environ["EVENTS_TOPIC_PREFIX"] = prefix
    return prefix


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE mv_station_case_kpis, mv_crime_trends, mv_evidence_integrity, "
                "dash_case, dash_consumed_events RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def emit(_topic_prefix):
    producer = AIOKafkaProducer(bootstrap_servers=os.environ["EVENTS_KAFKA_BOOTSTRAP"])
    await producer.start()

    async def _emit(event_type: str, payload: dict, **over) -> dict:
        env = make_envelope(event_type, payload, **over)
        topic = _topic_prefix + _BASE_TOPIC[event_type]
        await producer.send_and_wait(topic, json.dumps(env).encode())
        return env

    try:
        yield _emit
    finally:
        await producer.stop()


@pytest_asyncio.fixture
async def consumer(_topic_prefix):
    c = DashboardConsumer(
        SessionLocal,
        group_id=f"dash-test-{uuid.uuid4().hex}",
        topics=consumed_topics(),
    )
    await c.start()
    try:
        yield c
    finally:
        await c.stop()
