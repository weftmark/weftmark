import asyncio
import os
import shutil
import warnings
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock

import psycopg2
import pytest
import pyweaving.render as _pwr
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Font patch — must run at import time (rendering tests require it)
# ---------------------------------------------------------------------------


def _patch_pyweaving_font() -> None:
    data_dir = Path(os.path.dirname(_pwr.__file__)) / "data"
    target = data_dir / "Arial.ttf"
    if target.exists():
        return
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/Arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    ]
    for src in candidates:
        if src.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, target)
            return
    pytest.skip("No suitable system font found to patch PyWeaving — skipping render tests")


_patch_pyweaving_font()


# ---------------------------------------------------------------------------
# Mock OIDC before app.main is imported — prevents network calls in lifespan
# ---------------------------------------------------------------------------

import app.routers.auth as _auth_mod  # noqa: E402

_auth_mod.load_oidc_metadata = AsyncMock(return_value=None)

from app.deps import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.user import User  # noqa: E402

# ---------------------------------------------------------------------------
# Test database configuration
# ---------------------------------------------------------------------------
# Defaults work with the docker-compose db exposed at localhost:5433.
# CI sets POSTGRES_HOST=postgres POSTGRES_PORT=5432 POSTGRES_PASSWORD=ci_test_password.

_PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
_PG_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
_PG_USER = os.getenv("POSTGRES_USER", "weaving_user")
_PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
_PG_TEST_DB = "test_weaving_site"

_TEST_DB_URL = f"postgresql+asyncpg://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/{_PG_TEST_DB}"

_DB_AVAILABLE = False
_test_engine = None
_TestSessionLocal = None


def _make_engine():
    global _test_engine, _TestSessionLocal
    if _test_engine is None:
        _test_engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
        _TestSessionLocal = async_sessionmaker(
            _test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
    return _test_engine, _TestSessionLocal


def _ensure_test_database() -> None:
    conn = psycopg2.connect(
        host=_PG_HOST,
        port=_PG_PORT,
        user=_PG_USER,
        password=_PG_PASSWORD,
        dbname="postgres",
        connect_timeout=5,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_PG_TEST_DB,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {_PG_TEST_DB}")
    cur.close()
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    global _DB_AVAILABLE
    db_ok = False
    local_engine = None

    try:
        _ensure_test_database()
        local_engine, _ = _make_engine()

        async def _create():
            async with local_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(_create())
        db_ok = True
        _DB_AVAILABLE = True
    except Exception as exc:
        warnings.warn(f"Test database unavailable ({exc}). DB tests will be skipped.", stacklevel=2)

    yield

    if db_ok and local_engine is not None:

        async def _drop():
            async with local_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await local_engine.dispose()

        try:
            asyncio.run(_drop())
        except Exception:
            pass


@pytest.fixture
async def db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    if not _DB_AVAILABLE:
        pytest.skip("Database not available")
    _, TestSessionLocal = _make_engine()
    async with TestSessionLocal() as session:
        yield session
    # Session is now closed. Use a fresh connection for truncation so any
    # dirty state or failed flush in the test session does not affect cleanup.
    async with TestSessionLocal() as cleanup:
        table_names = ", ".join(Base.metadata.tables.keys())
        await cleanup.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        await cleanup.commit()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="test@example.com",
        display_name="Test User",
        oidc_sub="test-oidc-sub-001",
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        display_name="Admin User",
        oidc_sub="admin-oidc-sub-001",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(db_session: AsyncSession, admin_user: User) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_get_current_user() -> User:
        return admin_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
