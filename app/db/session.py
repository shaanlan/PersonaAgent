from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db() -> None:
    global engine, session_factory
    settings = get_settings()
    url = settings.sqlalchemy_database_url
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1].split("?")[0]
        if db_path and db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_async_engine(url, **kwargs)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def dispose_db() -> None:
    global engine, session_factory
    if engine is not None:
        await engine.dispose()
    engine = None
    session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if session_factory is None:
        init_db()
    assert session_factory is not None
    return session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
