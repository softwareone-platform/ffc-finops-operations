import logging
from contextlib import asynccontextmanager

import fastapi_pagination
from fastapi import FastAPI

from app import settings
from app.db import verify_db_connection
from app.routers import entitlements, organizations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover
    # NOTE: the lifespan is not executed when running the tests (thus the pragma: no cover)
    #       There is a way to change that with florimondmanca/asgi-lifespan but it's not
    #       needed for now as the lifespan is only used to verify the DB connection.
    #
    # refs:
    #     * https://fastapi.tiangolo.com/advanced/async-tests/#run-it
    #     * https://github.com/florimondmanca/asgi-lifespan#usage

    await verify_db_connection()
    yield


tags_metadata = [
    {
        "name": "Billing",
        "description": "Endpoints to manage billing data",
    },
    {
        "name": "Provisioning and Account Management",
        "description": "Endpoints for account provisioning and management",
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

app.include_router(entitlements.router, prefix="/billing/entitlements", tags=["Billing"])
app.include_router(
    organizations.router,
    prefix="/account/organizations",
    tags=["Provisioning and Account Management"],
)
