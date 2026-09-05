"""Test fixtures for training-service.

Two moving parts:

* training-service itself runs in-process (ASGITransport) against a dedicated
  ``training_db_test`` database.
* iam-service runs as a **subprocess** on a free port against its own
  dedicated ``identity_db_training_e2e`` database, so tests obtain real RS256
  access tokens through the genuine login -> MFA -> verify flow.
  training-service's JWKS client is pointed at that spawned iam-service, so
  token signatures are verified for real.

DB / auth env vars are set here *before* ``app`` is imported, since
``app.db`` / ``app.config`` read them at import time.
"""
import base64
import datetime as dt
import hashlib
import os
import pathlib
import socket
import subprocess
import time
import uuid

import httpx

# --- paths -------------------------------------------------------------------
_HERE = pathlib.Path(__file__).resolve().parent
_SCAFFOLD = _HERE.parents[1]
_IAM_DIR = _SCAFFOLD / "iam-service"
_IAM_PY = _IAM_DIR / ".venv" / "bin" / "python"

_PG = {
    "host": os.getenv("TRAINING_DB_HOST", "localhost"),
    "port": os.getenv("TRAINING_DB_PORT", "5432"),
    "user": os.getenv("TRAINING_DB_USER", "pmp"),
    "password": os.getenv("TRAINING_DB_PASSWORD", "pmp_dev_only"),
}
TEST_DB = "training_db_test"
_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{TEST_DB}"

os.environ["TRAINING_DATABASE_URL"] = f"postgresql+asyncpg://{_DSN}"
os.environ["TRAINING_DATABASE_URL_SYNC"] = f"postgresql+psycopg2://{_DSN}"

# --- spawned iam-service config --------------------------------------------
_IAM_DB = "identity_db_training_e2e"
_IAM_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{_IAM_DB}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IAM_PORT = int(os.getenv("TRAINING_TEST_IAM_PORT", str(_free_port())))
_IAM_BASE = f"http://127.0.0.1:{_IAM_PORT}"

_IAM_JWT_PEM = str(_HERE / ".e2e-iam-jwt-private.pem")
_IAM_ENV = {
    **os.environ,
    "IAM_DATABASE_URL": f"postgresql+asyncpg://{_IAM_DSN}",
    "IAM_DATABASE_URL_SYNC": f"postgresql+psycopg2://{_IAM_DSN}",
    "IAM_JWT_PRIVATE_KEY_PATH": _IAM_JWT_PEM,
    "IAM_JWT_ISSUER": "pmp-iam-service",
    "IAM_MFA_ENC_KEY": base64.urlsafe_b64encode(
        hashlib.sha256(b"training-e2e-mfa-key").digest()
    ).decode(),
    "IAM_ACCESS_TOKEN_TTL": "900",
}

# training-service verifies tokens against the spawned iam-service
os.environ["TRAINING_IAM_JWKS_URL"] = f"{_IAM_BASE}/api/v1/auth/jwks"
os.environ["TRAINING_JWT_ISSUER"] = "pmp-iam-service"

# --- event bus ------------------------------------------------------------
# The in-app relay stays off in tests; outbox tests drive OutboxRelay.drain_once
# explicitly. Topic names are prefixed per test run so a real Kafka broker can be
# shared without cross-run bleed. The background recompute task is likewise off
# by default; recompute tests drive RecomputeTask.sweep_once directly.
os.environ["EVENTS_RELAY_ENABLED"] = "0"
os.environ.setdefault("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")
os.environ["EVENTS_TOPIC_PREFIX"] = f"trnt_{uuid.uuid4().hex[:8]}."
os.environ["TRAINING_RECOMPUTE_ENABLED"] = "0"

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

engine = create_async_engine(os.environ["TRAINING_DATABASE_URL"], poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db.engine = engine
_db.SessionLocal = SessionLocal

from app.events import OutboxRelay, topic_for  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Certification, Course  # noqa: E402
from app.services.recompute_task import RecomputeTask  # noqa: E402

# badge -> seeded role. "Training Officer" holds training.cert.{read,write}
# (full CRUD, docs Section 2.3); "Auditor" holds neither.
_E2E_USERS = {
    "E2E-TRAIN": "Training Officer",
    "E2E-NONE": "Auditor",
}
_E2E_PASSWORD = "E2e!TestPassw0rd"
_totp_secrets: dict[str, str] = {}


# --------------------------------------------------------------------------- #
# database helpers
# --------------------------------------------------------------------------- #
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
        except httpx.HTTPError as exc:  # not up yet
            last = exc
        time.sleep(0.3)
    raise RuntimeError(f"iam-service did not become ready at {url}: {last}")


def _iam_enroll_mfa(badge: str) -> None:
    """One-time TOTP enrolment; caches the secret for the rest of the session."""
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
    """Real login -> MFA verify against the spawned iam-service (already enrolled)."""
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


# --------------------------------------------------------------------------- #
# session fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _training_database():
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
def token_train(iam_server) -> str:
    return iam_access_token("E2E-TRAIN")


@pytest.fixture(scope="session")
def token_none(iam_server) -> str:
    return iam_access_token("E2E-NONE")


# --------------------------------------------------------------------------- #
# per-test fixtures
# --------------------------------------------------------------------------- #
def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_train(token_train) -> dict:
    return bearer(token_train)


@pytest.fixture
def auth_none(token_none) -> dict:
    return bearer(token_none)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE officer_certifications, certifications, courses, "
                "outbox_events RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def outbox_relay():
    """A real OutboxRelay wired to the dev Kafka broker; caller drives drain_once()."""
    relay = OutboxRelay(SessionLocal)
    await relay.start()
    try:
        yield relay
    finally:
        await relay.stop()


@pytest_asyncio.fixture
async def recompute_task():
    return RecomputeTask(SessionLocal)


@pytest.fixture
def read_kafka():
    """read_kafka(event_type, expected=1, timeout=10) -> list[envelope dict]."""
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


@pytest_asyncio.fixture
async def make_course():
    async def _make(**overrides) -> Course:
        async with SessionLocal() as session:
            course = Course(
                title=overrides.get("title", f"Course-{uuid.uuid4().hex[:6]}"),
                validity_months=overrides.get("validity_months", 12),
                mandatory=overrides.get("mandatory", False),
            )
            session.add(course)
            await session.commit()
            await session.refresh(course)
            return course

    return _make


@pytest_asyncio.fixture
async def make_certification(make_course):
    async def _make(**overrides) -> Certification:
        course = overrides.get("course") or await make_course()
        async with SessionLocal() as session:
            cert = Certification(course_id=course.id)
            session.add(cert)
            await session.commit()
            await session.refresh(cert)
            return cert

    return _make


@pytest.fixture
def today() -> dt.date:
    return dt.date.today()
