from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage
from sqlalchemy import ColumnExpressionArgument

from app.db.handlers import NotFoundError
from app.db.models import System
from app.dependencies import SystemId, SystemRepository
from app.enums import AccountType
from app.pagination import paginate
from app.schemas import SystemCreate, SystemRead, SystemUpdate, from_orm

# ============
# Dependancies
# ============


async def common_extra_conditions(auth_ctx: CurrentAuthContext) -> list[ColumnExpressionArgument]:
    conditions: list[ColumnExpressionArgument] = []

    if auth_ctx.account.type == AccountType.AFFILIATE:
        conditions.append(System.owner == auth_ctx.account)

    return conditions


CommonConditions = Annotated[list[ColumnExpressionArgument], Depends(common_extra_conditions)]


async def fetch_system_or_404(
    id: SystemId,
    system_repo: SystemRepository,
    extra_conditions: CommonConditions,
) -> System:
    try:
        return await system_repo.get(id=id, extra_conditions=extra_conditions)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ======
# Routes
# ======


router = APIRouter()


@router.get("", response_model=LimitOffsetPage[SystemRead])
async def get_systems(
    system_repo: SystemRepository,
    auth_ctx: CurrentAuthContext,
    extra_conditions: CommonConditions,
):
    return await paginate(
        system_repo,
        SystemRead,
        extra_conditions=extra_conditions,
    )


@router.post("", response_model=SystemRead, status_code=status.HTTP_201_CREATED)
async def create_system(data: SystemCreate):  # pragma: no cover
    pass


@router.get("/{id}", response_model=SystemRead)
async def get_system_by_id(system: Annotated[System, Depends(fetch_system_or_404)]):
    return from_orm(SystemRead, system)


@router.put("/{id}", response_model=SystemRead)
async def update_system(id: SystemId, data: SystemUpdate):  # pragma: no cover
    pass


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_by_id(id: SystemId):  # pragma: no cover
    pass


@router.post("/{id}/disable", response_model=SystemRead)
async def disable_system(id: SystemId):  # pragma: no cover
    pass


@router.post("/{id}/enable", response_model=SystemRead)
async def enable_system(id: SystemId):  # pragma: no cover
    pass
