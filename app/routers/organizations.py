from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app import settings
from app.auth import get_current_system
from app.db.handlers import ConstraintViolationError, NotFoundError
from app.db.models import Organization, System
from app.pagination import paginate
from app.repositories import OrganizationRepository
from app.schemas import OrganizationCreate, OrganizationRead, from_orm, to_orm
from app.utils import get_api_modifier_jwt_token

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[OrganizationRead])
async def get_organizations(
    organization_repo: OrganizationRepository, system: System = Depends(get_current_system)
):
    return await paginate(organization_repo, OrganizationRead)


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(data: OrganizationCreate, organization_repo: OrganizationRepository):
    db_organization: Organization | None = None
    try:
        db_organization = await organization_repo.create(to_orm(data, Organization))
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
            db_organization = await organization_repo.update(
                db_organization.id,
                {
                    "organization_id": ffc_organization["id"],
                },
            )
            return from_orm(OrganizationRead, db_organization)
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
        db_organization = await organization_repo.get(id=id)
        return from_orm(OrganizationRead, db_organization)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
