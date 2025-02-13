import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app import settings
from app.db.db import DBSession, get_tx_db_session
from app.db.handlers import AccountHandler, AccountUserHandler, NotFoundError, UserHandler
from app.db.models import Account, AccountUser, User
from app.dependencies import CurrentAuthContext
from app.enums import AccountStatus, AccountType, AccountUserStatus, UserStatus
from app.schemas import (
    AccountUserCreate,
    AccountUserRead,
    UserAcceptInvitation,
    UserRead,
    UserResetPassword,
    UserUpdate,
    from_orm,
)

router = APIRouter()


@router.get("", response_model=LimitOffsetPage[UserRead])
async def get_users():
    pass


@router.post(
    "",
    response_model=AccountUserRead,
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    auth_context: CurrentAuthContext,
    db_session: DBSession,
    data: AccountUserCreate,
):
    user_handler = UserHandler(db_session)
    account_handler = AccountHandler(db_session)
    accountuser_handler = AccountUserHandler(db_session)
    account = None

    if auth_context.account.type == AccountType.AFFILIATE:
        if data.account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Affiliate accounts can only invite users to the same Account.",
            )
        account = auth_context.account
    else:
        if not data.account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Operations accounts must provide an account to invite a User.",
            )
        try:
            account = await account_handler.get(
                data.account.id,
                [Account.status == AccountStatus.ACTIVE],
            )
        except NotFoundError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No Active Account has been found with ID {data.account.id}.",
            )

    user = await user_handler.first(
        User.email == data.user.email,
        User.status != UserStatus.DELETED,
    )
    if not user:
        user = User(
            email=data.user.email,
            name=data.user.name,
            status=UserStatus.DRAFT,
        )

    if user.status == UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"The user {user.email} cannot be invited " "because it is disabled."),
        )
    if user.id:
        account_user = await accountuser_handler.get_account_user(
            account_id=account.id,
            user_id=user.id,
            extra_conditions=[AccountUser.status != AccountUserStatus.DELETED],
        )
        if account_user:
            msg = (
                "already belong"
                if account_user.status == AccountUserStatus.ACTIVE
                else "has already been invited"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The user {user.email} {msg} to the account: {account.id}.",
            )
    account_user = AccountUser(
        user=user,
        account=account,
        status=AccountUserStatus.INVITED,
        invitation_token=secrets.token_urlsafe(settings.invitation_token_length),
        invitation_token_expires_at=datetime.now(UTC)
        + timedelta(days=settings.invitation_token_expires_days),
    )
    db_session.expunge_all()
    async with get_tx_db_session() as tx_session:
        if not user.id:
            user_handler = UserHandler(tx_session)
            user = await user_handler.create(user)
        accountuser_handler = AccountUserHandler(tx_session)
        account_user = await accountuser_handler.create(account_user)
        return from_orm(AccountUserRead, account_user)


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
