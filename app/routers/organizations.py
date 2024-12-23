from fastapi import APIRouter
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.models import OrganizationRead
from app.pagination import paginate
from app.repositories import OrganizationRepository

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[OrganizationRead])
async def get_organizations(organization_repo: OrganizationRepository):
    return await paginate(organization_repo)
