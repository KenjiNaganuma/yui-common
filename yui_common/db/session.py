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
        _engine = create_async_engine(db_url, echo=False, pool_pre_ping=True, pool_recycle=300)
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

# yui_common/middleware/session.py
from starlette.middleware.sessions import SessionMiddleware

def setup_session_middleware(app):
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SESSION_SECRET_KEY"),
        session_cookie=os.getenv("SESSION_COOKIE_NAME", "yui_session"),
        domain=os.getenv("SESSION_DOMAIN"),
        https_only=os.getenv("SESSION_HTTPS_ONLY", "true").lower() == "true",
    )
