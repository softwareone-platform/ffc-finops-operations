from uuid import UUID

import svcs
from fastapi import APIRouter, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.api_clients import APIModifierClient
from app.api_clients.optscale import OptscaleClient
from app.auth import CurrentSystem
from app.db.handlers import NotFoundError
from app.db.models import Organization
from app.enums import CloudAccountType
from app.pagination import paginate
from app.repositories import OrganizationRepository
from app.schemas import CloudAccountRead, OrganizationCreate, OrganizationRead, from_orm
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


@router.get("/{id}", response_model=OrganizationRead)
async def get_organization_by_id(id: UUID, organization_repo: OrganizationRepository):
    try:
        db_organization = await organization_repo.get(id=id)
        return from_orm(OrganizationRead, db_organization)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("/{id}/cloud-accounts", response_model=list[CloudAccountRead])
async def get_cloud_accounts_by_organization_id(
    id: UUID,
    organization_repo: OrganizationRepository,
    services: svcs.fastapi.DepContainer,
):
    try:
        db_organization = await organization_repo.get(id=id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    if db_organization.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {db_organization.name} has no associated "
                "FinOps for Cloud organization"
            ),
        )

    optscale_client = await services.aget(OptscaleClient)

    async with wrap_http_error_in_502(
        f"Error fetching cloud accounts for organization {db_organization.name}"
    ):
        response = await optscale_client.fetch_cloud_accounts_for_organization(
            organization_id=db_organization.organization_id
        )

    cloud_accounts = response.json()["cloud_accounts"]

    return [
        CloudAccountRead(
            id=acc["id"],
            organization_id=db_organization.id,
            type=CloudAccountType(acc["type"]),
            resources_changed_this_month=acc["details"]["tracked"],
            expenses_so_far_this_month=acc["details"]["cost"],
            expenses_forecast_this_month=acc["details"]["forecast"],
        )
        for acc in cloud_accounts
    ]


@router.get("/{organization_id}/cloud-accounts/{cloud_account_id}", response_model=CloudAccountRead)
async def get_cloud_account_by_id(
    organization_id: UUID,
    cloud_account_id: UUID,
    organization_repo: OrganizationRepository,
    services: svcs.fastapi.DepContainer,
):
    try:
        db_organization = await organization_repo.get(id=organization_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    if db_organization.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Organization {db_organization.name} has no associated "
                "FinOps for Cloud organization"
            ),
        )

    optscale_client = await services.aget(OptscaleClient)

    async with wrap_http_error_in_502(f"Error fetching cloud account with ID {cloud_account_id}"):
        response = await optscale_client.fetch_cloud_account_by_id(cloud_account_id)

    cloud_account = response.json()

    return CloudAccountRead(
        id=cloud_account["id"],
        organization_id=db_organization.id,
        type=CloudAccountType(cloud_account["type"]),
        resources_changed_this_month=cloud_account["details"]["tracked"],
        expenses_so_far_this_month=cloud_account["details"]["cost"],
        expenses_forecast_this_month=cloud_account["details"]["forecast"],
    )
