from fastapi import APIRouter, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.collections import EntitlementCollection
from app.db import DBSession
from app.models import EntitlementCreate, EntitlementRead, EntitlementUpdate
from app.repositories import EntitlementRepository

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[EntitlementRead])
async def get_entitlements(session: DBSession):
    entitlements = EntitlementCollection(repository=EntitlementRepository(session=session))
    return await entitlements.fetch_page()


@router.get("/{id}", response_model=EntitlementRead)
async def get_entitlement_by_id(id: str, session: DBSession):
    entitlements = EntitlementCollection(repository=EntitlementRepository(session=session))
    return await entitlements.get(id=id)


@router.post("/", response_model=EntitlementRead, status_code=status.HTTP_201_CREATED)
async def create_entitlement(data: EntitlementCreate, session: DBSession):
    entitlements = EntitlementCollection(repository=EntitlementRepository(session=session))
    return await entitlements.create(data=data)


@router.patch("/{id}", response_model=EntitlementRead)
async def update_entitlement(id: str, data: EntitlementUpdate, session: DBSession):
    entitlements = EntitlementCollection(repository=EntitlementRepository(session=session))
    return await entitlements.update(id=id, data=data)
