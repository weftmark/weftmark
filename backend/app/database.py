from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# NullPool engine for Celery tasks: each asyncio.run() call creates a new event loop,
# which invalidates pooled asyncpg connections. NullPool creates a fresh connection
# per session, avoiding "Future attached to a different loop" errors.
_celery_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

CeleryAsyncSession = async_sessionmaker(
    _celery_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
