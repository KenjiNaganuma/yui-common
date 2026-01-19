# yui/common/db/session.py

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DBNAME_APP = os.getenv("DBNAME_APP")

DATABASE_URL = (
    f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DBNAME_APP}"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"server_settings": {"search_path": "app,kdp,ai,public"}},
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# common/db/session.py

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Depends 専用。
    HTTPリクエスト単位で session lifecycle を管理する。
    """
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
