from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import settings


class AsyncTxSession(AsyncSession):
    pass


db_engine = create_async_engine(
    str(settings.postgres_async_url),
    echo=settings.debug,
    future=True,
)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async_session = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@asynccontextmanager
async def get_tx_db_session() -> AsyncGenerator[AsyncSession]:
    async_session = async_sessionmaker(
        bind=db_engine, class_=AsyncTxSession, expire_on_commit=False
    )
    async with async_session() as session:
        async with session.begin() as transaction:
            yield session
            await transaction.commit()


DBSession = Annotated[AsyncSession, Depends(get_db_session)]


async def verify_db_connection():  # pragma: no cover
    async with asynccontextmanager(get_db_session)() as session:
        result = await session.execute(text("SELECT 1"))

        if result.one()[0] != 1:
            raise RuntimeError("Could not verify database connection")
