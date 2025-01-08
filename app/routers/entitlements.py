from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.auth import CurrentSystem
from app.db.db import DBSession
from app.db.handlers import NotFoundError
from app.db.models import Entitlement
from app.enums import EntitlementStatus
from app.pagination import paginate
from app.repositories import EntitlementRepository
from app.schemas import EntitlementCreate, EntitlementRead, from_orm, to_orm

router = APIRouter()


@router.get("/", response_model=LimitOffsetPage[EntitlementRead])
async def get_entitlements(entitlement_repo: EntitlementRepository):
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


async def fetch_entitlement_or_404(
    id: UUID, entitlement_repo: EntitlementRepository
) -> Entitlement:
    try:
        return await entitlement_repo.get(id=id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("/{id}", response_model=EntitlementRead)
async def get_entitlement_by_id(
    entitlement: Annotated[Entitlement, Depends(fetch_entitlement_or_404)],
):
    return from_orm(EntitlementRead, entitlement)


@router.post("/{id}/terminate", response_model=EntitlementRead)
async def terminate_entitlement(
    entitlement: Annotated[Entitlement, Depends(fetch_entitlement_or_404)],
    session: DBSession,
    system: CurrentSystem,
):
    if entitlement.status == EntitlementStatus.TERMINATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Entitlement is already terminated"
        )

    if entitlement.status != EntitlementStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Only active entitlements can be terminated,"
                f" current status is {entitlement.status.value}"
            ),
        )

    entitlement.status = EntitlementStatus.TERMINATED
    entitlement.terminated_by = system
    entitlement.updated_by = system
    entitlement.terminated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(entitlement)

    return from_orm(EntitlementRead, entitlement)
