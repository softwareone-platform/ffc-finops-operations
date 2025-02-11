import logging

import fastapi_pagination
import svcs
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import Request

from app import settings
from app.api_clients import BaseAPIClient
from app.auth.auth import get_authentication_context
from app.db import verify_db_connection
from app.routers import accounts, auth, employees, entitlements, organizations, systems, users

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


app = FastAPI(
    title="FinOps for Cloud Operations API",
    description="API to be used to manage FinOps for Cloud tool",
    openapi_tags=tags_metadata,
    version="4.0.0",
    root_path="/ops/v1",
    debug=settings.debug,
    lifespan=lifespan,
)


fastapi_pagination.add_pagination(app)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    This middleware intercepts all the ValidationError exceptions raised by Pydantic
    when there is a mismatch with the defined Model.
    FastAPI wraps it in RequestValidationError, which is a subclass of ValidationError,
    for requests.
    This middleware in the end returns a 400 status code instead of the
    default 422 for validation errors.

    """
    return JSONResponse(
        status_code=400,
        content={
            "detail": [
                {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ],
            "body": str(exc.body) if hasattr(exc, "body") else None,
        },
    )

# TODO: Add healthcheck

app.include_router(
    entitlements.router,
    prefix="/entitlements",
    dependencies=[Depends(get_authentication_context)],
    tags=["Billing"],
)
app.include_router(
    organizations.router,
    prefix="/organizations",
    dependencies=[Depends(get_authentication_context)],
    tags=["FinOps for Cloud Provisioning"],
)
app.include_router(
    employees.router,
    prefix="/employees",
    dependencies=[Depends(get_authentication_context)],
    tags=["FinOps for Cloud Provisioning"],
)
app.include_router(
    accounts.router,
    prefix="/accounts",
    dependencies=[Depends(get_authentication_context)],
    tags=["Portal Administration"],
)


app.include_router(
    users.router,
    prefix="/users",
    dependencies=[Depends(get_authentication_context)],
    tags=["Portal Settings"],
)
app.include_router(
    systems.router,
    prefix="/systems",
    dependencies=[Depends(get_authentication_context)],
    tags=["Portal Settings"],
)
app.include_router(auth.router, prefix="/auth", tags=["Auth"])

if __name__ == "__main__":
    uvicorn.run("main:app", port=8080, host="0.0.0.0", reload=True)  # nosec B104
