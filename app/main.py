import logging

import fastapi_pagination
import svcs
from fastapi import Depends, FastAPI

from app import settings
from app.api_clients import BaseAPIClient
from app.auth import get_current_system
from app.db import verify_db_connection
from app.routers import entitlements, organizations, users

logger = logging.getLogger(__name__)


@svcs.fastapi.lifespan
async def lifespan(app: FastAPI, registry: svcs.Registry):
    # TODO: Move the database setup to a svcs service and
    #       use the function bellow its healthcheck
    await verify_db_connection()

    for client_name, client_cls in BaseAPIClient.get_clients_by_name().items():
        logging.info("Registering %s API client as a service", client_name)
        registry.register_factory(svc_type=client_cls, factory=client_cls)

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
    dependencies=[Depends(get_current_system)],
)


fastapi_pagination.add_pagination(app)

# TODO: Add healthcheck

app.include_router(entitlements.router, prefix="/entitlements", tags=["Operations"])
app.include_router(organizations.router, prefix="/organizations", tags=["Operations"])
app.include_router(users.router, prefix="/users", tags=["Operations"])
