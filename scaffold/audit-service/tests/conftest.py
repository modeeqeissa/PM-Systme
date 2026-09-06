"""Test fixtures for audit-service.

* audit-service runs in-process (ASGITransport). Its ORM engine connects as the
  least-privilege ``audit_service_app`` role against ``audit_db_test``.
* A separate owner (``pmp``) engine handles migrations and the DB-layer
  append-only / tamper tests.
* iam-service runs as a subprocess for real ``audit.read`` tokens.
* A real Kafka broker (infra) is used with a per-run topic prefix; tests publish
  event envelopes and drive AuditConsumer.process_available() explicitly.
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

_HERE = pathlib.Path(__file__).resolve().parent
_SCAFFOLD = _HERE.parents[1]
_IAM_DIR = _SCAFFOLD / "iam-service"
_IAM_PY = _IAM_DIR / ".venv" / "bin" / "python"

_PG = {"host": "localhost", "port": "5432", "user": "pmp", "password": "pmp_dev_only"}
_TEST_DB = "audit_db_test"
_APP_ROLE = "audit_service_app"
_APP_PW = "audit_app_dev_only"

_OWNER_SYNC = f"postgresql+psycopg2://pmp:pmp_dev_only@localhost:5432/{_TEST_DB}"
_OWNER_ASYNC = f"postgresql+asyncpg://pmp:pmp_dev_only@localhost:5432/{_TEST_DB}"
_APP_ASYNC = f"postgresql+asyncpg://{_APP_ROLE}:{_APP_PW}@localhost:5432/{_TEST_DB}"

os.environ["AUDIT_DATABASE_URL"] = _APP_ASYNC
os.environ["AUDIT_DATABASE_URL_SYNC"] = _OWNER_SYNC
os.environ["AUDIT_CONSUMER_ENABLED"] = "0"
os.environ.setdefault("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")
os.environ["EVENTS_TOPIC_PREFIX"] = f"aud_{uuid.uuid4().hex[:8]}."

_IAM_DB = "identity_db_audit_e2e"
_IAM_DSN = f"pmp:pmp_dev_only@localhost:5432/{_IAM_DB}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IAM_PORT = int(os.getenv("AUDIT_TEST_IAM_PORT", str(_free_port())))
_IAM_BASE = f"http://127.0.0.1:{_IAM_PORT}"
_IAM_ENV = {
    **os.environ,
    "IAM_DATABASE_URL": f"postgresql+asyncpg://{_IAM_DSN}",
    "IAM_DATABASE_URL_SYNC": f"postgresql+psycopg2://{_IAM_DSN}",
    "IAM_JWT_PRIVATE_KEY_PATH": str(_HERE / ".e2e-iam-jwt-private.pem"),
    "IAM_JWT_ISSUER": "pmp-iam-service",
    "IAM_MFA_ENC_KEY": base64.urlsafe_b64encode(
        hashlib.sha256(b"audit-e2e-mfa-key").digest()
    ).decode(),
    "IAM_ACCESS_TOKEN_TTL": "900",
}
os.environ["AUDIT_IAM_JWKS_URL"] = f"{_IAM_BASE}/api/v1/auth/jwks"
os.environ["AUDIT_JWT_ISSUER"] = "pmp-iam-service"

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

app_engine = create_async_engine(_APP_ASYNC, poolclass=NullPool)
AppSession = async_sessionmaker(app_engine, expire_on_commit=False)
_db.engine = app_engine
_db.SessionLocal = AppSession

owner_engine = create_async_engine(_OWNER_ASYNC, poolclass=NullPool)
OwnerSession = async_sessionmaker(owner_engine, expire_on_commit=False)

from app.events import AuditConsumer  # noqa: E402
from app.events.topics import consumed_topics  # noqa: E402
from app.main import app  # noqa: E402

_USERS = {"AUD-READ": "Auditor", "AUD-NONE": "Patrol Officer"}
_PASSWORD = "Aud1t!Testpwxx"
_totp_secrets: dict[str, str] = {}

_BASE_TOPIC = {
    "CaseOpened": "case.opened",
    "CaseStatusChanged": "case.status_changed",
    "ArrestRecorded": "case.arrest_recorded",
    "StatementRecorded": "case.statement_recorded",
    "CourtProceedingRecorded": "case.court_proceeding_recorded",
    "CaseOfficerAssigned": "case.officer_assigned",
    "CaseOfficerUnassigned": "case.officer_unassigned",
    "EvidenceLogged": "evidence.logged",
    "CustodyEventRecorded": "evidence.custody_recorded",
    "EvidenceHashMismatch": "evidence.hash_mismatch",
    "UserCreated": "user.created",
    "UserDeactivated": "user.deactivated",
    "UserRoleReassigned": "user.role_reassigned",
    "AccountLockedOut": "account.locked_out",
    "OfficerCreated": "hr.officer_created",
    "OfficerUpdated": "hr.officer_updated",
    "OfficerSupervisorChanged": "hr.officer_supervisor_changed",
    "UnitCreated": "hr.unit_created",
    "AssignmentRecorded": "hr.assignment_recorded",
    "TransferRequested": "hr.transfer_requested",
    "TransferStatusChanged": "hr.transfer_status_changed",
    "PromotionRecorded": "hr.promotion_recorded",
    "LeaveRequested": "hr.leave_requested",
    "LeaveStatusChanged": "hr.leave_status_changed",
    "DisciplineRecordCreated": "hr.discipline_record_created",
    "DisciplineRecordUpdated": "hr.discipline_record_updated",
    "DisciplineRecordDeleted": "hr.discipline_record_deleted",
    "PerformanceReviewRecorded": "hr.performance_review_recorded",
    "PerformanceReviewUpdated": "hr.performance_review_updated",
    "PerformanceReviewDeleted": "hr.performance_review_deleted",
    "CourseCreated": "training.course_created",
    "CourseUpdated": "training.course_updated",
    "CourseDeleted": "training.course_deleted",
    "CertificationCreated": "training.certification_created",
    "CertificationDeleted": "training.certification_deleted",
    "OfficerCertificationIssued": "training.officer_certification_issued",
    "OfficerCertificationStatusChanged": "training.officer_certification_status_changed",
    "MeetingLogged": "community.meeting_logged",
    "ConcernLogged": "community.concern_logged",
    "ConcernStatusChanged": "community.concern_status_changed",
    "FollowUpActionCreated": "community.follow_up_action_created",
    "FollowUpActionStatusChanged": "community.follow_up_action_status_changed",
    "IntegrationConfigUpdated": "integration.config_updated",
    "ExternalSystemCallLogged": "integration.external_system_call_logged",
    "SomethingUnmapped": "case.opened",
}


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


def owner_conn():
    return psycopg2.connect(dbname=_TEST_DB, **_PG)


def app_role_conn():
    return psycopg2.connect(
        dbname=_TEST_DB, host="localhost", port="5432",
        user=_APP_ROLE, password=_APP_PW,
    )


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
    import datetime as dt

    env = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "aggregate_type": over.get("aggregate_type", "x"),
        "aggregate_id": over.get("aggregate_id", str(uuid.uuid4())),
        "actor_id": over.get("actor_id", str(uuid.uuid4())),
        "actor_role": over.get("actor_role", "Investigator"),
        "service": over.get("service", "case-service"),
        "payload": payload,
    }
    env.update({k: v for k, v in over.items() if k in env})
    return env


# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _audit_database():
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
def token_read(iam_server) -> str:
    return iam_access_token("AUD-READ")


@pytest.fixture(scope="session")
def token_none(iam_server) -> str:
    return iam_access_token("AUD-NONE")


@pytest.fixture
def auth_read(token_read) -> dict:
    return bearer(token_read)


@pytest.fixture
def auth_none(token_none) -> dict:
    return bearer(token_none)


@pytest.fixture(autouse=True)
def _topic_prefix():
    """Per-test topic namespace so a fresh consumer group never re-reads another
    test's events."""
    prefix = f"aud_{uuid.uuid4().hex}."
    os.environ["EVENTS_TOPIC_PREFIX"] = prefix
    return prefix


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE audit_logs, consumed_events RESTART IDENTITY CASCADE")
        )
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def emit(_topic_prefix):
    """emit(event_type, payload, **envelope_overrides) -> envelope. Publishes to Kafka."""
    producer = AIOKafkaProducer(bootstrap_servers=os.environ["EVENTS_KAFKA_BOOTSTRAP"])
    await producer.start()

    async def _emit(event_type: str, payload: dict, **over) -> dict:
        env = make_envelope(event_type, payload, **over)
        topic = _topic_prefix + _BASE_TOPIC.get(event_type, "case.opened")
        await producer.send_and_wait(topic, json.dumps(env).encode())
        return env

    try:
        yield _emit
    finally:
        await producer.stop()


@pytest_asyncio.fixture
async def consumer(_topic_prefix):
    c = AuditConsumer(
        AppSession,
        group_id=f"audit-test-{uuid.uuid4().hex}",
        topics=consumed_topics(),
    )
    await c.start()
    try:
        yield c
    finally:
        await c.stop()
