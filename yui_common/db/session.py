# yui_common/db/session.py
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_sessionmaker = None


def _build_database_url() -> str:
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    dbname = os.getenv("DBNAME_APP")

    if not all([user, password, host, port, dbname]):
        raise RuntimeError("Database environment variables are not fully set")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"


def get_engine():
    global _engine
    if _engine is None:
        db_url = _build_database_url()
        _engine = create_async_engine(db_url, echo=False)
    return _engine


def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine()
        _sessionmaker = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    return _sessionmaker


from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        yield session
