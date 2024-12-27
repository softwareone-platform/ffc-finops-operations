from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app import settings
from app.db.handlers import ConstraintViolationError, NotFoundError
from app.models import Organization, OrganizationCreate, OrganizationRead
from app.pagination import paginate
from app.repositories import OrganizationRepository
from app.utils import get_api_modifier_jwt_token

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[OrganizationRead])
async def get_organizations(organization_repo: OrganizationRepository):
    return await paginate(organization_repo)


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(data: OrganizationCreate, organization_repo: OrganizationRepository):
    organization: Organization | None = None
    try:
        organization = await organization_repo.create(data)
    except ConstraintViolationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization with this external ID already exists: {data.external_id}.",
        )

    try:
        async with httpx.AsyncClient(base_url=settings.api_modifier_base_url) as client:
            response = await client.post(
                "/admin/organizations",
                headers={"Authorization": f"Bearer {get_api_modifier_jwt_token()}"},
                json={
                    "org_name": data.name,
                    "user_id": data.user_id,
                    "currency": data.currency,
                },
            )
            response.raise_for_status()
            ffc_organization = response.json()
            organization.organization_id = ffc_organization["id"]
            return await organization_repo.update(organization.id, organization)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Error creating organization in FinOps for Cloud: "
                f"{e.response.status_code} - {e.response.text}.",
            ),
        ) from e


@router.get("/{id}", response_model=OrganizationRead)
async def get_organization_by_id(id: UUID, organization_repo: OrganizationRepository):
    try:
        return await organization_repo.get(id=id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
