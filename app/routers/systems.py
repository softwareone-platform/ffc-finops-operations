from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage
from sqlalchemy import ColumnExpressionArgument

from app.db.handlers import ConstraintViolationError, NotFoundError
from app.db.models import System
from app.dependencies import CurrentAuthContext, SystemId, SystemRepository
from app.enums import AccountType, SystemStatus
from app.pagination import paginate
from app.schemas import SystemCreate, SystemRead, SystemUpdate, from_orm

# ============
# Dependencies
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
async def update_system(
    system: Annotated[System, Depends(fetch_system_or_404)],
    system_repo: SystemRepository,
    data: SystemUpdate,
):
    try:
        system = await system_repo.update(system, data.model_dump())
    except ConstraintViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A system with the same external ID already exists.",
        ) from e

    return from_orm(SystemRead, system)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_by_id(
    system: Annotated[System, Depends(fetch_system_or_404)],
    system_repo: SystemRepository,
    auth_ctx: CurrentAuthContext,
):
    if system == auth_ctx.system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A system cannot delete itself.",
        )

    if system.status == SystemStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already deleted.",
        )

    await system_repo.soft_delete(system)


@router.post("/{id}/disable", response_model=SystemRead)
async def disable_system(
    system: Annotated[System, Depends(fetch_system_or_404)],
    system_repo: SystemRepository,
    auth_ctx: CurrentAuthContext,
):
    if system == auth_ctx.system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A system cannot disable itself.",
        )

    if system.status != SystemStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"System's status is '{system.status._value_}'; "
                "only active systems can be disabled."
            ),
        )

    system = await system_repo.update(system, {"status": SystemStatus.DISABLED})
    return from_orm(SystemRead, system)


@router.post("/{id}/enable", response_model=SystemRead)
async def enable_system(
    system: Annotated[System, Depends(fetch_system_or_404)],
    system_repo: SystemRepository,
):
    # no need to check for a system re-enabling itself as such a request
    # will fail earlier anyway during the authorization phase

    if system.status != SystemStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"System's status is '{system.status._value_}'; "
                "only disabled systems can be enabled."
            ),
        )

    system = await system_repo.update(system, {"status": SystemStatus.ACTIVE})
    return from_orm(SystemRead, system)
