from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage
from sqlalchemy import ColumnExpressionArgument

from app.auth.context import auth_context
from app.db.handlers import NotFoundError
from app.db.models import System
from app.dependencies import SystemId, SystemRepository
from app.enums import AccountType
from app.schemas import SystemCreate, SystemRead, SystemUpdate, from_orm

router = APIRouter()


async def fetch_system_or_404(id: SystemId, system_repo: SystemRepository) -> System:
    extra_conditions: list[ColumnExpressionArgument] = []

    auth_account = auth_context.get().account

    if auth_account.type == AccountType.AFFILIATE:
        extra_conditions.append(System.owner == auth_account)

    try:
        return await system_repo.get(id=id, extra_conditions=extra_conditions)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("", response_model=LimitOffsetPage[SystemRead])
async def get_systems():
    pass


@router.post("", response_model=SystemRead, status_code=status.HTTP_201_CREATED)
async def create_system(data: SystemCreate):
    pass


@router.get("/{id}", response_model=SystemRead)
async def get_system_by_id(system: Annotated[System, Depends(fetch_system_or_404)]):
    return from_orm(SystemRead, system)


@router.put("/{id}", response_model=SystemRead)
async def update_system(id: SystemId, data: SystemUpdate):
    pass


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_by_id(id: SystemId):
    pass


@router.post("/{id}/disable", response_model=SystemRead)
async def disable_system(id: SystemId):
    pass


@router.post("/{id}/enable", response_model=SystemRead)
async def enable_system(id: SystemId):
    pass
