from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.base import get_db_engine, get_db_session, verify_db_connection

DBEngine = Annotated[AsyncEngine, Depends(get_db_engine)]
DBSession = Annotated[AsyncSession, Depends(get_db_session)]

__all__ = ["DBSession", "verify_db_connection"]
