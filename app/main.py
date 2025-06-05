import logging
from contextlib import asynccontextmanager
from functools import partial

import fastapi_pagination
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute, APIRouter

from app.conf import get_settings
from app.db.base import configure_db_engine, verify_db_connection
from app.dependencies.auth import authentication_required, check_operations_account
from app.openapi import generate_openapi_spec
from app.routers import (
    accounts,
    auth,
    chargesfiles,
    employees,
    entitlements,
    expenses,
    organizations,
    systems,
    users,
)
from app.telemetry import setup_fastapi_instrumentor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.debug = settings.debug
    configure_db_engine(settings)
    await verify_db_connection(settings)
    yield


tags_metadata = [
    {
        "name": "Auth",
        "description": "Operations Portal Authentication",
    },
    {
        "name": "Portal Administration",
        "description": "Operations Portal administration edpoints.",
    },
    {
        "name": "Portal Settings",
        "description": "Operations Portal settings edpoints.",
    },
    {
        "name": "FinOps for Cloud Provisioning",
        "description": "Endpoints for account provisioning in FinOps for Cloud",
    },
    {
        "name": "Billing",
        "description": "FinOps for Cloud Billing management endpoints.",
    },
]


def setup_custom_serialization(router: APIRouter):
    for api_route in router.routes:
        if (
            isinstance(api_route, APIRoute)
            and hasattr(api_route, "response_model")
            and api_route.response_model
        ):
            api_route.response_model_exclude_none = True


def setup_app():
    app = FastAPI(
        title="FinOps for Cloud Operations API",
        description="API to be used to manage FinOps for Cloud tool",
        openapi_tags=tags_metadata,
        version="4.0.0",
        root_path="/ops/v1",
        lifespan=lifespan,
    )
    fastapi_pagination.add_pagination(app)

    for router in (
        entitlements.router,
        organizations.router,
        employees.router,
        accounts.router,
        users.router,
        chargesfiles.router,
        expenses.router,
    ):
        setup_custom_serialization(router)

    # TODO: Add healthcheck
    app.include_router(
        expenses.router,
        prefix="/expenses",
        dependencies=[Depends(check_operations_account)],
        tags=["Billing"],
    )
    app.include_router(
        entitlements.router,
        prefix="/entitlements",
        dependencies=[Depends(authentication_required)],
        tags=["Billing"],
    )
    app.include_router(
        chargesfiles.router,
        prefix="/charges",
        dependencies=[Depends(authentication_required)],
        tags=["Billing"],
    )
    app.include_router(
        organizations.router,
        prefix="/organizations",
        dependencies=[Depends(authentication_required)],
        tags=["FinOps for Cloud Provisioning"],
    )
    app.include_router(
        employees.router,
        prefix="/employees",
        dependencies=[Depends(authentication_required)],
        tags=["FinOps for Cloud Provisioning"],
    )
    app.include_router(
        accounts.router,
        prefix="/accounts",
        dependencies=[Depends(authentication_required)],
        tags=["Portal Administration"],
    )
    app.include_router(
        users.router,
        prefix="/users",
        tags=["Portal Settings"],
    )
    app.include_router(
        systems.router,
        prefix="/systems",
        dependencies=[Depends(authentication_required)],
        tags=["Portal Settings"],
    )

    app.include_router(auth.router, prefix="/auth", tags=["Auth"])

    app.openapi = partial(generate_openapi_spec, app)

    setup_fastapi_instrumentor(
        get_settings(),
        app,
    )
    return app


app = setup_app()
