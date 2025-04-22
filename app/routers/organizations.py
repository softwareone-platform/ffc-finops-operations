from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select

from app.auth.context import auth_context
from app.db.handlers import ConstraintViolationError, NotFoundError
from app.db.models import Organization
from app.dependencies.api_clients import APIModifierClient, OptscaleAuthClient, OptscaleClient
from app.dependencies.auth import check_operations_account
from app.dependencies.db import OrganizationRepository
from app.dependencies.path import OrganizationId
from app.enums import DatasourceType
from app.pagination import LimitOffsetPage, paginate
from app.rql import OrganizationRules, RQLQuery
from app.schemas.core import convert_model_to_schema
from app.schemas.employees import EmployeeRead
from app.schemas.organizations import (
    DatasourceRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.utils import wrap_exc_in_http_response, wrap_http_error_in_502

router = APIRouter(dependencies=[Depends(check_operations_account)])


@router.get("", response_model=LimitOffsetPage[OrganizationRead])
async def get_organizations(
    organization_repo: OrganizationRepository,
    base_query: Select = Depends(RQLQuery(OrganizationRules())),
):
    return await paginate(organization_repo, OrganizationRead, base_query=base_query)


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    organization_repo: OrganizationRepository,
    api_modifier_client: APIModifierClient,
):
    db_organization: Organization | None = None
    defaults = data.model_dump(exclude_unset=True, exclude={"user_id"})
    defaults["created_by"] = auth_context.get().get_actor()
    defaults["updated_by"] = auth_context.get().get_actor()
    db_organization, created = await organization_repo.get_or_create(
        defaults=defaults,
        operations_external_id=data.operations_external_id,
    )

    if not created:
        if db_organization.linked_organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "An Organization with external ID "
                    f"`{data.operations_external_id}` already exists."
                ),
            )
        if db_organization.name != data.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"The name of a partially created Organization with "
                    f"external ID {data.operations_external_id}  doesn't match the "
                    f"current request: {db_organization.name}."
                ),
            )

    with wrap_http_error_in_502("Error creating organization in FinOps for Cloud"):
        response = await api_modifier_client.create_organization(
            org_name=db_organization.name, user_id=data.user_id, currency=data.currency
        )

        ffc_organization = response.json()
        db_organization = await organization_repo.update(
            db_organization.id,
            {
                "linked_organization_id": ffc_organization["id"],
            },
        )
        return convert_model_to_schema(OrganizationRead, db_organization)


async def fetch_organization_or_404(
    organization_id: OrganizationId, organization_repo: OrganizationRepository
) -> Organization:
    try:
        return await organization_repo.get(id=organization_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization_by_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
):
    return convert_model_to_schema(OrganizationRead, organization)


@router.get("/{organization_id}/datasources", response_model=list[DatasourceRead])
async def get_datasources_by_organization_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    optscale_client: OptscaleClient,
):
    if organization.linked_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {organization.name} has no associated FinOps for Cloud organization."
            ),
        )

    with wrap_http_error_in_502(f"Error fetching datasources for organization {organization.name}"):
        response = await optscale_client.fetch_datasources_for_organization(
            organization_id=organization.linked_organization_id
        )

    datasources = response.json()["cloud_accounts"]

    return [
        DatasourceRead(
            id=acc["id"],
            name=acc["name"],
            type=DatasourceType(acc["type"]),
            parent_id=acc["parent_id"],
            resources_charged_this_month=acc["details"]["resources"],
            expenses_so_far_this_month=acc["details"]["cost"],
            expenses_forecast_this_month=acc["details"]["forecast"],
        )
        for acc in datasources
    ]


@router.get("/{organization_id}/datasources/{datasource_id}", response_model=DatasourceRead)
async def get_datasource_by_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    datasource_id: UUID,
    optscale_client: OptscaleClient,
):
    if organization.linked_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {organization.name} has no associated FinOps for Cloud organization."
            ),
        )

    with wrap_http_error_in_502(f"Error fetching cloud account with ID {datasource_id}"):
        response = await optscale_client.fetch_datasource_by_id(datasource_id)

    datasource = response.json()

    return DatasourceRead(
        id=datasource["id"],
        name=datasource["name"],
        type=DatasourceType(datasource["type"]),
        parent_id=datasource["parent_id"],
        resources_charged_this_month=datasource["details"]["resources"],
        expenses_so_far_this_month=datasource["details"]["cost"],
        expenses_forecast_this_month=datasource["details"]["forecast"],
    )


@router.get("/{organization_id}/employees", response_model=list[EmployeeRead])
async def get_employees_by_organization_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    optscale_client: OptscaleClient,
):
    if organization.linked_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {organization.name} has no associated FinOps for Cloud organization."
            ),
        )

    with wrap_http_error_in_502(f"Error fetching employees for organization {organization.name}"):
        response = await optscale_client.fetch_users_for_organization(
            organization_id=organization.linked_organization_id
        )

    users = response.json()["employees"]

    return [
        EmployeeRead(
            id=user["id"],
            email=user["user_email"],
            display_name=user["user_display_name"],
            created_at=user["created_at"],
            last_login=user["last_login"],
            roles_count=len(user["assignments"]),
        )
        for user in users
    ]


@router.post(
    "/{organization_id}/employees/{user_id}/make-admin",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def make_organization_user_admin(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    user_id: UUID,
    optscale_auth_client: OptscaleAuthClient,
    optscale_client: OptscaleClient,
):
    with wrap_http_error_in_502("Error making employee admin in FinOps for Cloud"):
        # check user exists in optscale
        response = await optscale_client.fetch_user_by_id(str(user_id))
        user = response.json()
        # assign admin role of current organization to the user
        await optscale_auth_client.make_user_admin(
            str(organization.linked_organization_id),
            user["auth_user_id"],
        )


@router.put("/{organization_id}", response_model=OrganizationRead)
async def update_organization(
    db_organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    organization_repo: OrganizationRepository,
    optscale_client: OptscaleClient,
    data: OrganizationUpdate,
):
    original_external_id = db_organization.operations_external_id
    external_id_changed = (
        data.operations_external_id is not None
        and original_external_id != data.operations_external_id
    )
    name_changed = data.name is not None and db_organization.name != data.name

    if name_changed and db_organization.linked_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {db_organization.name} has no associated "
                "FinOps for Cloud organization."
            ),
        )

    if external_id_changed:
        # If the external ID is changed, we need to first change it in the DB as there is a unique
        # constraint on it and if it fails, then we can immediately return an error response and not
        # even make an API call to the API modifier

        with wrap_exc_in_http_response(
            ConstraintViolationError,
            "An organization with the same operations_external_id already exists.",
        ):
            db_organization = await organization_repo.update(
                db_organization,
                {"operations_external_id": data.operations_external_id},
            )

    if not name_changed:
        return convert_model_to_schema(OrganizationRead, db_organization)

    # If the name has changed, we need to first change it in Optscale as this API call can fail
    # and change it in the DB only if the API call is successful

    try:
        # mypy isn't smart enough to unrderstand that by this point both
        # data.name and db_organization.linked_organization_id are not None
        # due to the checks above, so we're ignoring the type checks here

        await optscale_client.update_organization_name(
            db_organization.linked_organization_id,  # type: ignore[arg-type]
            data.name,  # type: ignore[arg-type]
        )
    except httpx.HTTPStatusError as e:
        if external_id_changed:
            await organization_repo.update(
                db_organization,
                {"operations_external_id": original_external_id},
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Error changing the organization's name in FinOps for Cloud: "
                f"{e.response.status_code} - {e.response.text}."
            ),
        ) from e

    # The name change on the optscale side was successful, so we can now update the name in the DB
    db_organization = await organization_repo.update(db_organization, {"name": data.name})

    return convert_model_to_schema(OrganizationRead, db_organization)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_by_id(id: str):
    pass
