from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.db.handlers import NotFoundError
from app.models import EntitlementCreate, EntitlementRead
from app.pagination import paginate
from app.repositories import EntitlementRepository

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[EntitlementRead])
async def get_entitlements(entitlement_repo: EntitlementRepository):
    return await paginate(entitlement_repo)


@router.get("/{id}", response_model=EntitlementRead)
async def get_entitlement_by_id(id: UUID, entitlement_repo: EntitlementRepository):
    try:
        return await entitlement_repo.get(id=id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post("/", response_model=EntitlementRead, status_code=status.HTTP_201_CREATED)
async def create_entitlement(data: EntitlementCreate, entitlement_repo: EntitlementRepository):
    return await entitlement_repo.create(data=data)
