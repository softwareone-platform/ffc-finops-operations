from fastapi import APIRouter, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.schemas import (
    AccountUserCreate,
    AccountUserRead,
    UserAcceptInvitation,
    UserRead,
    UserResetPassword,
    UserUpdate,
)

router = APIRouter()


@router.get("", response_model=LimitOffsetPage[UserRead])
async def get_users():
    pass


@router.post("", response_model=AccountUserRead)
async def invite_user(data: AccountUserCreate):
    pass


@router.put("/{id}", response_model=UserRead)
async def update_user(id: str, data: UserUpdate):
    pass


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(id: str):
    pass


@router.get("/{id}/accounts", response_model=list[AccountUserRead])
async def get_user_accounts(id: str):
    pass


@router.post("/{id}/disable", response_model=UserRead)
async def disable_user(id: str):
    pass


@router.post("/{id}/enable", response_model=UserRead)
async def enable_user(id: str):
    pass


@router.post("/{id}/resend-invitation", response_model=UserRead)
async def resend_user_invitation(id: str):
    pass


@router.get("/{id}", response_model=UserRead)
async def get_user_by_id(id: str, token: str | None = None):
    # if token is provided no authentication is needed but
    # an AccountOperator in status invited must exist with
    # user id and token and the token must not be expired
    pass


@router.post("/{id}/accept-invitation", response_model=UserRead)
async def accept_user_invitation(id: str, data: UserAcceptInvitation):
    # Public endpoint
    # an AccountOperator in status invited must exist with
    # user id and token and the token must not be expired
    # credentials are needed to be set only if the Operator is in draft status
    pass


@router.post("/{id}/reset-password", response_model=UserRead)
async def reset_user_password(id: str, data: UserResetPassword):
    pass
