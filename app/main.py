import logging
from contextlib import asynccontextmanager

import fastapi_pagination
from fastapi import FastAPI

from app import settings
from app.db import verify_db_connection
from app.routers import entitlements, organizations, users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await verify_db_connection()
    yield


tags_metadata = [
    {
        "name": "Operations",
        "description": "Endpoint for managing FinOps for Cloud",
    },
]


app = FastAPI(
    title="FinOps for Cloud Operations API",
    description="API to be used by Operators to manage FinOps for Cloud tool",
    openapi_tags=tags_metadata,
    root_path="/v1",
    debug=settings.debug,
    lifespan=lifespan,
)

fastapi_pagination.add_pagination(app)


# TODO: Add healthcheck

app.include_router(entitlements.router, prefix="/entitlements", tags=["Operations"])
app.include_router(organizations.router, prefix="/organizations", tags=["Operations"])
app.include_router(users.router, prefix="/users", tags=["Operations"])
