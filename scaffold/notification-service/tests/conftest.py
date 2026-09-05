"""Test fixtures for notification-service.

Two moving parts:

* notification-service itself runs in-process (ASGITransport) against a
  dedicated ``notification_db_test`` database.
* iam-service runs as a **subprocess** on a free port against its own
  dedicated ``identity_db_notification_e2e`` database, so tests obtain real
  RS256 access tokens through the genuine login -> MFA -> verify flow.

DB / auth env vars are set here *before* ``app`` is imported, since
``app.db`` / ``app.config`` read them at import time.
"""
import base64
import hashlib
import json
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
    "host": os.getenv("NOTIFICATION_DB_HOST", "localhost"),
    "port": os.getenv("NOTIFICATION_DB_PORT", "5432"),
    "user": os.getenv("NOTIFICATION_DB_USER", "pmp"),
    "password": os.getenv("NOTIFICATION_DB_PASSWORD", "pmp_dev_only"),
}
TEST_DB = "notification_db_test"
_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{TEST_DB}"

os.environ["NOTIFICATION_DATABASE_URL"] = f"postgresql+asyncpg://{_DSN}"
os.environ["NOTIFICATION_DATABASE_URL_SYNC"] = f"postgresql+psycopg2://{_DSN}"

# --- spawned iam-service config --------------------------------------------
_IAM_DB = "identity_db_notification_e2e"
_IAM_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{_IAM_DB}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IAM_PORT = int(os.getenv("NOTIFICATION_TEST_IAM_PORT", str(_free_port())))
_IAM_BASE = f"http://127.0.0.1:{_IAM_PORT}"

_IAM_JWT_PEM = str(_HERE / ".e2e-iam-jwt-private.pem")
_IAM_ENV = {
    **os.environ,
    "IAM_DATABASE_URL": f"postgresql+asyncpg://{_IAM_DSN}",
    "IAM_DATABASE_URL_SYNC": f"postgresql+psycopg2://{_IAM_DSN}",
    "IAM_JWT_PRIVATE_KEY_PATH": _IAM_JWT_PEM,
    "IAM_JWT_ISSUER": "pmp-iam-service",
    "IAM_MFA_ENC_KEY": base64.urlsafe_b64encode(
        hashlib.sha256(b"notification-e2e-mfa-key").digest()
    ).decode(),
    "IAM_ACCESS_TOKEN_TTL": "900",
}

os.environ["NOTIFICATION_IAM_JWKS_URL"] = f"{_IAM_BASE}/api/v1/auth/jwks"
os.environ["NOTIFICATION_JWT_ISSUER"] = "pmp-iam-service"

# --- event bus / background workers -----------------------------------------
# Both the consumer and delivery worker stay off in tests; drive them
# explicitly (NotificationConsumer.process_available / DeliveryWorker.run_once).
os.environ["NOTIFICATION_CONSUMER_ENABLED"] = "0"
os.environ.setdefault("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")
os.environ["EVENTS_TOPIC_PREFIX"] = f"notift_{uuid.uuid4().hex[:8]}."
os.environ["NOTIFICATION_DELIVERY_ENABLED"] = "0"

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

engine = create_async_engine(os.environ["NOTIFICATION_DATABASE_URL"], poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db.engine = engine
_db.SessionLocal = SessionLocal

from app.events import NotificationConsumer, consumed_topics  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Notification, OfficerUserMap  # noqa: E402
from app.services.delivery import DeliveryWorker  # noqa: E402

# Any authenticated user can read their own notifications — no permission
# claim is checked — so a single role with unrelated permissions is enough.
_E2E_USERS = {"E2E-USER-1": "Auditor", "E2E-USER-2": "Auditor"}
_E2E_PASSWORD = "E2e!TestPassw0rd"
_totp_secrets: dict[str, str] = {}
_user_ids: dict[str, str] = {}

_BASE_TOPIC = {
    "OfficerCreated": "hr.officer_created",
    "TransferStatusChanged": "hr.transfer_status_changed",
    "LeaveStatusChanged": "hr.leave_status_changed",
    "OfficerCertificationStatusChanged": "training.officer_certification_status_changed",
    "FollowUpActionStatusChanged": "community.follow_up_action_status_changed",
    "AccountLockedOut": "account.locked_out",
}


def make_envelope(event_type: str, payload: dict, **over) -> dict:
    import datetime as dt

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "aggregate_type": over.get("aggregate_type", "x"),
        "aggregate_id": over.get("aggregate_id", str(uuid.uuid4())),
        "actor_id": over.get("actor_id", str(uuid.uuid4())),
        "actor_role": over.get("actor_role", "HR Officer"),
        "service": over.get("service", "hr-service"),
        "payload": payload,
    }


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
        token = verify.json()["access_token"]
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        _user_ids[badge] = claims["sub"]
        return token


# --------------------------------------------------------------------------- #
# session fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _notification_database():
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
def token_user1(iam_server) -> str:
    return iam_access_token("E2E-USER-1")


@pytest.fixture(scope="session")
def token_user2(iam_server) -> str:
    return iam_access_token("E2E-USER-2")


# --------------------------------------------------------------------------- #
# per-test fixtures
# --------------------------------------------------------------------------- #
def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_user1(token_user1) -> dict:
    return bearer(token_user1)


@pytest.fixture
def auth_user2(token_user2) -> dict:
    return bearer(token_user2)


@pytest.fixture
def user1_id(token_user1) -> str:
    return _user_ids["E2E-USER-1"]


@pytest.fixture
def user2_id(token_user2) -> str:
    return _user_ids["E2E-USER-2"]


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE notifications, officer_user_map, consumed_events "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _topic_prefix():
    """Per-test topic namespace so a fresh consumer group never re-reads
    another test's events."""
    prefix = f"notift_{uuid.uuid4().hex}."
    os.environ["EVENTS_TOPIC_PREFIX"] = prefix
    return prefix


@pytest_asyncio.fixture
async def emit(_topic_prefix):
    """emit(event_type, payload, **envelope_overrides) -> envelope. Publishes to Kafka."""
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
    c = NotificationConsumer(
        SessionLocal,
        group_id=f"notification-test-{uuid.uuid4().hex}",
        topics=consumed_topics(),
    )
    await c.start()
    try:
        yield c
    finally:
        await c.stop()


@pytest_asyncio.fixture
async def delivery_worker():
    return DeliveryWorker(SessionLocal)


@pytest_asyncio.fixture
async def make_officer_map():
    async def _make(officer_id: uuid.UUID, user_id: uuid.UUID) -> OfficerUserMap:
        async with SessionLocal() as session:
            row = OfficerUserMap(officer_id=officer_id, user_id=user_id)
            session.add(row)
            await session.commit()
            return row

    return _make


@pytest_asyncio.fixture
async def make_notification():
    async def _make(**overrides) -> Notification:
        async with SessionLocal() as session:
            n = Notification(
                recipient_user_id=overrides.get("recipient_user_id", uuid.uuid4()),
                channel=overrides.get("channel", "in_app"),
                template_code=overrides.get("template_code", "ACCOUNT_LOCKED_OUT"),
                payload=overrides.get("payload", {}),
                status=overrides.get("status", "queued"),
            )
            session.add(n)
            await session.commit()
            await session.refresh(n)
            return n

    return _make
