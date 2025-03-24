from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.conf import AppSettings, Settings


def get_db_engine(settings: AppSettings) -> AsyncEngine:
    return create_async_engine(
        str(settings.postgres_async_url),
        echo=settings.debug,
        future=True,
    )


def get_sessionmaker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)


def get_db_sessionmaker(
    db_engine: AsyncEngine = Depends(get_db_engine),
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session(
    session_maker: async_sessionmaker[AsyncSession] = Depends(get_db_sessionmaker),
) -> AsyncGenerator[AsyncSession]:
    async with session_maker() as session:
        async with session.begin():
            yield session


async def verify_db_connection(settings: Settings):  # pragma: no cover
    db_engine = get_db_engine(settings)
    session_maker = get_db_sessionmaker(db_engine)

    async with asynccontextmanager(get_db_session)(session_maker) as session:
        result = await session.execute(text("SELECT 1"))

        if result.one()[0] != 1:
            raise RuntimeError("Could not verify database connection")
