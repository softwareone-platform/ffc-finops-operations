from typing import Annotated
from uuid import UUID

import svcs
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.api_clients import APIModifierClient
from app.api_clients.optscale import OptscaleClient
from app.auth import CurrentSystem
from app.db.handlers import NotFoundError
from app.db.models import Organization
from app.enums import DatasourceType
from app.pagination import paginate
from app.repositories import OrganizationRepository
from app.schemas import DatasourceRead, OrganizationCreate, OrganizationRead, UserRead, from_orm
from app.utils import wrap_http_error_in_502

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[OrganizationRead])
async def get_organizations(organization_repo: OrganizationRepository):
    return await paginate(organization_repo, OrganizationRead)


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    organization_repo: OrganizationRepository,
    current_system: CurrentSystem,
    services: svcs.fastapi.DepContainer,
):
    api_modifier_client = await services.aget(APIModifierClient)

    db_organization: Organization | None = None
    defaults = data.model_dump(exclude_unset=True, exclude={"user_id", "currency"})
    defaults["created_by"] = current_system
    defaults["updated_by"] = current_system
    db_organization, created = await organization_repo.get_or_create(
        defaults=defaults,
        external_id=data.external_id,
    )

    if not created:
        if db_organization.organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An Organization with external ID `{data.external_id}` already exists.",
            )
        if db_organization.name != data.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"The name of a partially created Organization with "
                    f"external ID {data.external_id}  doesn't match the "
                    f"current request: {db_organization.name}."
                ),
            )

    async with wrap_http_error_in_502("Error creating organization in FinOps for Cloud"):
        response = await api_modifier_client.create_organization(
            org_name=db_organization.name, user_id=data.user_id, currency=data.currency
        )

        ffc_organization = response.json()
        db_organization = await organization_repo.update(
            db_organization.id,
            {
                "organization_id": ffc_organization["id"],
            },
        )
        return from_orm(OrganizationRead, db_organization)


async def fetch_organization_or_404(
    organization_id: UUID, organization_repo: OrganizationRepository
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
    return from_orm(OrganizationRead, organization)


@router.get("/{organization_id}/datasources", response_model=list[DatasourceRead])
async def get_datasources_by_organization_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    services: svcs.fastapi.DepContainer,
):
    if organization.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {organization.name} has no associated "
                "FinOps for Cloud organization"
            ),
        )

    optscale_client = await services.aget(OptscaleClient)

    async with wrap_http_error_in_502(
        f"Error fetching datasources for organization {organization.name}"
    ):
        response = await optscale_client.fetch_datasources_for_organization(
            organization_id=organization.organization_id
        )

    datasources = response.json()["cloud_accounts"]

    return [
        DatasourceRead(
            id=acc["id"],
            organization_id=organization.id,
            type=DatasourceType(acc["type"]),
            resources_changed_this_month=acc["details"]["tracked"],
            expenses_so_far_this_month=acc["details"]["cost"],
            expenses_forecast_this_month=acc["details"]["forecast"],
        )
        for acc in datasources
    ]


@router.get("/{organization_id}/datasources/{datasource_id}", response_model=DatasourceRead)
async def get_datasource_by_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    datasource_id: UUID,
    services: svcs.fastapi.DepContainer,
):
    if organization.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {organization.name} has no associated "
                "FinOps for Cloud organization"
            ),
        )

    optscale_client = await services.aget(OptscaleClient)

    async with wrap_http_error_in_502(f"Error fetching cloud account with ID {datasource_id}"):
        response = await optscale_client.fetch_datasource_by_id(datasource_id)

    datasource = response.json()

    return DatasourceRead(
        id=datasource["id"],
        organization_id=organization.id,
        type=DatasourceType(datasource["type"]),
        resources_changed_this_month=datasource["details"]["tracked"],
        expenses_so_far_this_month=datasource["details"]["cost"],
        expenses_forecast_this_month=datasource["details"]["forecast"],
    )


@router.get("/{organization_id}/users", response_model=list[UserRead])
async def get_users_by_organization_id(
    organization: Annotated[Organization, Depends(fetch_organization_or_404)],
    services: svcs.fastapi.DepContainer,
):
    if organization.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {organization.name} has no associated "
                "FinOps for Cloud organization"
            ),
        )

    optscale_client = await services.aget(OptscaleClient)

    async with wrap_http_error_in_502(f"Error fetching users for organization {organization.name}"):
        response = await optscale_client.fetch_users_for_organization(
            organization_id=organization.organization_id
        )

    users = response.json()["employees"]

    return [
        UserRead(
            id=user["id"],
            email=user["user_email"],
            display_name=user["user_display_name"],
            created_at=user["created_at"],
            last_login=user["last_login"],
            roles_count=len(user["assignments"]),
        )
        for user in users
    ]
