"""Test fixtures for evidence-service.

Moving parts:

* evidence-service runs in-process (ASGITransport). Its ORM engine connects as
  the least-privilege ``evidence_service_app`` role against ``evidence_db_test``
  - exactly like production - so tests exercise the real grants.
* A separate owner (``pmp``) engine is used for fixture setup / cleanup and for
  the DB-layer append-only tests.
* iam-service runs as a subprocess on a free port against ``identity_db_evi_e2e``
  so tests obtain real RS256 tokens through the genuine login -> MFA flow;
  evidence-service verifies their signatures against that iam-service's JWKS.

Env vars are set here *before* ``app`` is imported.
"""
import base64
import datetime as dt
import hashlib
import os
import pathlib
import shutil
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
    "host": os.getenv("EVIDENCE_DB_HOST", "localhost"),
    "port": os.getenv("EVIDENCE_DB_PORT", "5432"),
    "user": "pmp",
    "password": "pmp_dev_only",
}
_TEST_DB = "evidence_db_test"
_APP_ROLE = "evidence_service_app"
_APP_PW = "evidence_app_dev_only"

_OWNER_SYNC = f"postgresql+psycopg2://pmp:pmp_dev_only@{_PG['host']}:{_PG['port']}/{_TEST_DB}"
_OWNER_ASYNC = f"postgresql+asyncpg://pmp:pmp_dev_only@{_PG['host']}:{_PG['port']}/{_TEST_DB}"
_APP_ASYNC = f"postgresql+asyncpg://{_APP_ROLE}:{_APP_PW}@{_PG['host']}:{_PG['port']}/{_TEST_DB}"

os.environ["EVIDENCE_DATABASE_URL"] = _APP_ASYNC          # running service -> app role
os.environ["EVIDENCE_DATABASE_URL_SYNC"] = _OWNER_SYNC    # alembic -> owner
os.environ["EVIDENCE_VAULT_DIR"] = str(_HERE / ".evidence-vault-test")
os.environ["EVIDENCE_VAULT_KEY"] = base64.urlsafe_b64encode(
    hashlib.sha256(b"evidence-test-vault-key").digest()
).decode()

# --- spawned iam-service --------------------------------------------------
_IAM_DB = "identity_db_evi_e2e"
_IAM_DSN = f"pmp:pmp_dev_only@{_PG['host']}:{_PG['port']}/{_IAM_DB}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IAM_PORT = int(os.getenv("EVIDENCE_TEST_IAM_PORT", str(_free_port())))
_IAM_BASE = f"http://127.0.0.1:{_IAM_PORT}"
_IAM_ENV = {
    **os.environ,
    "IAM_DATABASE_URL": f"postgresql+asyncpg://{_IAM_DSN}",
    "IAM_DATABASE_URL_SYNC": f"postgresql+psycopg2://{_IAM_DSN}",
    "IAM_JWT_PRIVATE_KEY_PATH": str(_HERE / ".e2e-iam-jwt-private.pem"),
    "IAM_JWT_ISSUER": "pmp-iam-service",
    "IAM_MFA_ENC_KEY": base64.urlsafe_b64encode(
        hashlib.sha256(b"evi-e2e-mfa-key").digest()
    ).decode(),
    "IAM_ACCESS_TOKEN_TTL": "900",
}
os.environ["EVIDENCE_IAM_JWKS_URL"] = f"{_IAM_BASE}/api/v1/auth/jwks"
os.environ["EVIDENCE_JWT_ISSUER"] = "pmp-iam-service"

# --- event bus ---------------------------------------------------------------
os.environ["EVENTS_RELAY_ENABLED"] = "0"
os.environ.setdefault("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")
os.environ["EVENTS_TOPIC_PREFIX"] = f"evt_{uuid.uuid4().hex[:8]}."

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

app_engine = create_async_engine(_APP_ASYNC, poolclass=NullPool)
AppSession = async_sessionmaker(app_engine, expire_on_commit=False)
_db.engine = app_engine
_db.SessionLocal = AppSession

owner_engine = create_async_engine(_OWNER_ASYNC, poolclass=NullPool)
OwnerSession = async_sessionmaker(owner_engine, expire_on_commit=False)

from app.events import OutboxRelay, topic_for  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CustodyEvent, EvidenceItem  # noqa: E402

_EVI_USERS = {
    "EVI-FULL": "Evidence Custodian",  # vault.read + vault.write + custody.write
    "EVI-READ": "Patrol Officer",      # vault.read only
    "EVI-NONE": "Auditor",             # neither
}
_EVI_PASSWORD = "Ev1!denceTestpw"
_totp_secrets: dict[str, str] = {}


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


def app_role_conn():
    """psycopg2 connection AS the least-privilege application role."""
    return psycopg2.connect(
        dbname=_TEST_DB, host=_PG["host"], port=_PG["port"],
        user=_APP_ROLE, password=_APP_PW,
    )


def owner_conn():
    """psycopg2 connection AS the owner/superuser."""
    return psycopg2.connect(dbname=_TEST_DB, **_PG)


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


def _iam_enroll_mfa(badge: str) -> None:
    with httpx.Client(base_url=_IAM_BASE, timeout=10.0) as c:
        login = c.post(
            "/api/v1/auth/login",
            json={"badge_number": badge, "password": _EVI_PASSWORD},
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
            json={"badge_number": badge, "password": _EVI_PASSWORD},
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


# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _evidence_database():
    _recreate_database(_TEST_DB)
    cfg = Config(str(_HERE.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(_HERE.parent / "alembic"))
    command.upgrade(cfg, "head")
    vault_dir = pathlib.Path(os.environ["EVIDENCE_VAULT_DIR"])
    if vault_dir.exists():
        shutil.rmtree(vault_dir)
    yield
    if vault_dir.exists():
        shutil.rmtree(vault_dir)


@pytest.fixture(scope="session", autouse=True)
def iam_server():
    if not _IAM_PY.exists():
        pytest.skip(f"iam-service venv not found at {_IAM_PY}")
    _recreate_database(_IAM_DB)
    subprocess.run(
        [str(_IAM_PY), "-m", "alembic", "upgrade", "head"],
        cwd=_IAM_DIR, env=_IAM_ENV, check=True, capture_output=True,
    )
    for badge, role in _EVI_USERS.items():
        subprocess.run(
            [
                str(_IAM_PY), "-m", "scripts.create_user",
                "--badge", badge, "--password", _EVI_PASSWORD,
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
        for badge in _EVI_USERS:
            _iam_enroll_mfa(badge)
        yield _IAM_BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def token_full(iam_server) -> str:
    return iam_access_token("EVI-FULL")


@pytest.fixture(scope="session")
def token_read(iam_server) -> str:
    return iam_access_token("EVI-READ")


@pytest.fixture(scope="session")
def token_none(iam_server) -> str:
    return iam_access_token("EVI-NONE")


@pytest.fixture
def auth_full(token_full) -> dict:
    return bearer(token_full)


@pytest.fixture
def auth_read(token_read) -> dict:
    return bearer(token_read)


@pytest.fixture
def auth_none(token_none) -> dict:
    return bearer(token_none)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    # TRUNCATE does not fire the per-row append-only triggers on custody_events.
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE custody_events, evidence_items, outbox_events "
                "RESTART IDENTITY CASCADE"
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
    """A real OutboxRelay driven by the least-privilege app role; caller drives drain_once()."""
    relay = OutboxRelay(AppSession)
    await relay.start()
    try:
        yield relay
    finally:
        await relay.stop()


@pytest.fixture
def read_kafka():
    """read_kafka(event_type, expected=1, timeout=10) -> list[envelope dict]."""
    import asyncio
    import json

    from aiokafka import AIOKafkaConsumer

    async def _read(event_type: str, expected: int = 1, timeout: float = 10.0):
        consumer = AIOKafkaConsumer(
            topic_for(event_type),
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
                    out.extend(json.loads(m.value) for m in msgs)
        finally:
            await consumer.stop()
        return out

    return _read


@pytest_asyncio.fixture
async def make_item():
    """Insert a physical evidence item + its initial 'collected' custody event."""

    async def _make(**overrides) -> EvidenceItem:
        async with OwnerSession() as session:
            item = EvidenceItem(
                case_id=overrides.get("case_id", uuid.uuid4()),
                item_type=overrides.get("item_type", "physical"),
                description=overrides.get("description", "A physical exhibit"),
                collected_by=overrides.get("collected_by", uuid.uuid4()),
                collected_at=overrides.get(
                    "collected_at", dt.datetime.now(dt.timezone.utc)
                ),
                storage_ref=overrides.get("storage_ref"),
                sha256_hash=overrides.get("sha256_hash"),
                status=overrides.get("status", "logged"),
            )
            session.add(item)
            await session.flush()
            session.add(
                CustodyEvent(
                    evidence_id=item.id, action="collected", to_officer=item.collected_by
                )
            )
            await session.commit()
            await session.refresh(item)
            return item

    return _make
