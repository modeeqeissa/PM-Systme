"""Test fixtures for iam-service.

Runs against a dedicated ``identity_db_test`` database on the docker-compose
Postgres so dev ``identity_db`` is untouched. Env vars are set here *before*
``app`` is imported, since ``app.db`` / ``app.config`` read them at import time.
"""
import base64
import hashlib
import os
import uuid
from dataclasses import dataclass, field

_PG = {
    "host": os.getenv("IAM_DB_HOST", "localhost"),
    "port": os.getenv("IAM_DB_PORT", "5432"),
    "user": os.getenv("IAM_DB_USER", "pmp"),
    "password": os.getenv("IAM_DB_PASSWORD", "pmp_dev_only"),
}
TEST_DB = "identity_db_test"
_DSN = f"{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{TEST_DB}"

os.environ["IAM_DATABASE_URL"] = f"postgresql+asyncpg://{_DSN}"
os.environ["IAM_DATABASE_URL_SYNC"] = f"postgresql+psycopg2://{_DSN}"
os.environ["IAM_JWT_PRIVATE_KEY_PATH"] = os.path.join(
    os.path.dirname(__file__), ".test-jwt-private.pem"
)
os.environ["IAM_MFA_ENC_KEY"] = base64.urlsafe_b64encode(
    hashlib.sha256(b"iam-test-mfa-key").digest()
).decode()
os.environ["IAM_ACCESS_TOKEN_TTL"] = "900"

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

engine = create_async_engine(os.environ["IAM_DATABASE_URL"], poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_db.engine = engine
_db.SessionLocal = SessionLocal

from app.models import Role, User  # noqa: E402
from app.security import mfa, passwords, tokens  # noqa: E402
from app.services.rbac import effective_permissions, role_names  # noqa: E402
from app.main import app  # noqa: E402

_HERE = os.path.dirname(__file__)


def _recreate_test_database() -> None:
    conn = psycopg2.connect(dbname="postgres", **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (TEST_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
            cur.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _database():
    _recreate_test_database()
    cfg = Config(os.path.join(_HERE, os.pardir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_HERE, os.pardir, "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with engine.begin() as conn:
        # keep the seeded roles (id<=6) + permissions; drop test-created data
        await conn.execute(text("TRUNCATE users, sessions, user_roles CASCADE"))
        await conn.execute(text("DELETE FROM roles WHERE id > 6"))
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@dataclass
class SeededUser:
    id: uuid.UUID
    badge_number: str
    password: str
    station_id: uuid.UUID
    mfa_secret: str | None = None
    role_names: list[str] = field(default_factory=list)


@pytest_asyncio.fixture
async def make_user():
    async def _make(
        *,
        badge_number: str | None = None,
        password: str = "Sup3rSecret!pw",
        roles: list[str] | None = None,
        status: str = "active",
        with_mfa: bool = True,
    ) -> SeededUser:
        badge_number = badge_number or f"BADGE-{uuid.uuid4().hex[:8]}"
        station_id = uuid.uuid4()
        raw_secret = mfa.new_secret() if with_mfa else None
        async with SessionLocal() as session:
            role_rows = []
            if roles:
                from sqlalchemy import select

                role_rows = list(
                    (await session.scalars(select(Role).where(Role.name.in_(roles)))).all()
                )
            user = User(
                badge_number=badge_number,
                password_hash=passwords.hash_password(password),
                full_name="Test User",
                station_id=station_id,
                status=status,
                mfa_secret=mfa.encrypt_secret(raw_secret) if raw_secret else None,
                roles=role_rows,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return SeededUser(
                id=user.id,
                badge_number=badge_number,
                password=password,
                station_id=station_id,
                mfa_secret=raw_secret,
                role_names=roles or [],
            )

    return _make


@pytest_asyncio.fixture
async def access_token_for():
    """Mint a valid access token directly (skips the login/MFA dance)."""

    async def _mint(seeded: SeededUser) -> str:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        async with SessionLocal() as session:
            user = await session.scalar(
                select(User)
                .options(selectinload(User.roles).selectinload(Role.permissions))
                .where(User.id == seeded.id)
            )
            token, _ = tokens.issue_access_token(
                user_id=user.id,
                badge_number=user.badge_number,
                station_id=user.station_id,
                roles=role_names(user),
                permissions=effective_permissions(user),
            )
            return token

    return _mint


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
