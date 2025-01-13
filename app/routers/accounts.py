from fastapi import APIRouter, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    AccountUserRead,
)

router = APIRouter()


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
):
    pass


@router.get("", response_model=LimitOffsetPage[AccountRead])
async def get_accounts():
    pass


@router.get("/{id}", response_model=AccountRead)
async def get_account_by_id(id: str):
    pass


@router.put("/{id}", response_model=AccountRead)
async def update_account(id: str, data: AccountUpdate):
    pass


@router.get("/{id}/users", response_model=LimitOffsetPage[AccountUserRead])
async def list_account_users(id: str):
    pass


@router.delete("/{id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_account(id: str, user_id: str):
    pass
