import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def main():
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "weaving_site")
    user = os.environ.get("POSTGRES_USER", "postgres")
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    dsn = f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db}"
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM alembic_version WHERE version_num = '5b6c7d8e9f0a'"))
        rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
        print("After fix:", [r[0] for r in rows.fetchall()])
    await engine.dispose()


asyncio.run(main())
