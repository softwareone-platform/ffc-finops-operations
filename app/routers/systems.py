from uuid import UUID

from fastapi import APIRouter, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.schemas import SystemCreate, SystemRead, SystemUpdate

router = APIRouter()


@router.get("", response_model=LimitOffsetPage[SystemRead])
async def get_systems():
    pass


@router.post("", response_model=SystemRead, status_code=status.HTTP_201_CREATED)
async def create_system(
    data: SystemCreate,
):
    pass


@router.get("/{id}", response_model=SystemRead)
async def get_system_by_id(id: UUID):
    pass


@router.put("/{id}", response_model=SystemRead)
async def update_system(id: UUID, data: SystemUpdate):
    pass


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_by_id(id: UUID):
    pass


@router.post("/{id}/disable", response_model=SystemRead)
async def disable_system(id: UUID):
    pass


@router.post("/{id}/enable", response_model=SystemRead)
async def enable_system(id: UUID):
    pass
