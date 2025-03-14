import logging
from contextlib import asynccontextmanager
from functools import partial

import fastapi_pagination
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute, APIRouter

from app.auth.auth import authentication_required
from app.conf import get_settings
from app.db import verify_db_connection
from app.openapi import generate_openapi_spec
from app.routers import (
    accounts,
    auth,
    chargesfiles,
    employees,
    entitlements,
    organizations,
    systems,
    users,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Move the database setup to a svcs service and
    #       use the function bellow its healthcheck
    settings = get_settings()
    app.debug = settings.debug
    await verify_db_connection(settings)
    # for client_name, client_cls in BaseAPIClient.get_clients_by_name().items():
    #     logging.info("Registering %s API client as a service", client_name)
    #     registry.register_factory(svc_type=client_cls, factory=client_cls)

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
    ):
        setup_custom_serialization(router)

    # TODO: Add healthcheck
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

    return app


app = setup_app()
