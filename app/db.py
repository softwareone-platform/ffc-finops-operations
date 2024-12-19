from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app import settings

db_engine = create_async_engine(
    str(settings.postgres_async_url),
    echo=settings.debug,
    future=True,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async_session = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db_session)]


async def verify_db_connection():  # pragma: no cover
    async with asynccontextmanager(get_db_session)() as session:
        result = await session.exec(text("SELECT 1"))

        if result.one()[0] != 1:
            raise RuntimeError("Could not verify database connection")
