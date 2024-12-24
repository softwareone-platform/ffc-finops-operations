from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.auth import CurrentSystem
from app.db.handlers import NotFoundError
from app.db.models import Entitlement
from app.pagination import paginate
from app.repositories import EntitlementRepository
from app.schemas import EntitlementCreate, EntitlementRead, from_orm, to_orm

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[EntitlementRead])
async def get_entitlements(
    entitlement_repo: EntitlementRepository,
    system: CurrentSystem,
):
    return await paginate(entitlement_repo, EntitlementRead)


@router.post("/", response_model=EntitlementRead, status_code=status.HTTP_201_CREATED)
async def create_entitlement(
    data: EntitlementCreate,
    entitlement_repo: EntitlementRepository,
    system: CurrentSystem,
):
    entitlement = to_orm(data, Entitlement)
    entitlement.created_by = system
    entitlement.updated_by = system

    db_entitlement = await entitlement_repo.create(entitlement)
    return from_orm(EntitlementRead, db_entitlement)


@router.get("/{id}", response_model=EntitlementRead)
async def get_entitlement_by_id(
    id: UUID,
    entitlement_repo: EntitlementRepository,
    system: CurrentSystem,
):
    try:
        db_entitlement = await entitlement_repo.get(id=id)
        return from_orm(EntitlementRead, db_entitlement)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
