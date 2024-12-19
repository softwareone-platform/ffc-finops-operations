from fastapi import APIRouter
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.collections import OrganizationCollection
from app.db import DBSession
from app.models import OrganizationRead
from app.repositories import OrganizationRepository

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[OrganizationRead])
async def get_organizations(session: DBSession):
    organizations = OrganizationCollection(repository=OrganizationRepository(session=session))
    return await organizations.fetch_page()
