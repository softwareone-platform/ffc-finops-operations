import logging
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.auth.auth import authentication_required, check_operations_account
from app.conf import AppSettings
from app.db import DBEngine, DBSession, get_tx_db_session
from app.db.handlers import AccountHandler, AccountUserHandler, NotFoundError, UserHandler
from app.db.models import Account, AccountUser, User
from app.dependencies import CurrentAuthContext, UserId
from app.enums import AccountStatus, AccountType, AccountUserStatus, UserStatus
from app.hasher import pbkdf2_sha256
from app.schemas import (
    AccountUserCreate,
    AccountUserRead,
    UserAcceptInvitation,
    UserRead,
    UserResetPassword,
    UserUpdate,
    from_orm,
)

logger = logging.getLogger(__name__)

PWD_COMPLEXITY_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")


# ======
# Routes
# ======

router = APIRouter()


@router.get(
    "",
    dependencies=[Depends(authentication_required)],
    response_model=LimitOffsetPage[UserRead],
)
async def get_users():  # pragma: no cover
    pass  # not yet implemented


@router.post(
    "",
    dependencies=[Depends(authentication_required)],
    response_model=AccountUserRead,
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    auth_context: CurrentAuthContext,
    settings: AppSettings,
    db_engine: DBEngine,
    db_session: DBSession,
    data: AccountUserCreate,
):
    user_handler = UserHandler(db_session)
    account_handler = AccountHandler(db_session)
    accountuser_handler = AccountUserHandler(db_session)
    account = None

    if auth_context.account.type == AccountType.AFFILIATE:  # type: ignore
        if data.account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Affiliate accounts can only invite users to the same Account.",
            )
        account = auth_context.account  # type: ignore
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
    async with get_tx_db_session(db_engine) as tx_session:
        if not user.id:
            user_handler = UserHandler(tx_session)
            user = await user_handler.create(user)
        accountuser_handler = AccountUserHandler(tx_session)
        account_user = await accountuser_handler.create(account_user)
        return from_orm(AccountUserRead, account_user)


@router.put(
    "/{id}",
    dependencies=[Depends(authentication_required)],
    response_model=UserRead,
)
async def update_user(id: str, data: UserUpdate):  # pragma: no cover
    pass  # not yet implemented


@router.delete(
    "/{id}",
    dependencies=[Depends(check_operations_account)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(id: str):  # pragma: no cover
    pass  # not yet implemented


@router.get(
    "/{id}/accounts",
    dependencies=[Depends(authentication_required)],
    response_model=list[AccountUserRead],
)
async def get_user_accounts(id: str):  # pragma: no cover
    pass  # not yet implemented


@router.post(
    "/{id}/disable",
    dependencies=[Depends(authentication_required)],
    response_model=UserRead,
)
async def disable_user(id: str):  # pragma: no cover
    pass  # not yet implemented


@router.post(
    "/{id}/enable",
    dependencies=[Depends(authentication_required)],
    response_model=UserRead,
)
async def enable_user(id: str):  # pragma: no cover
    pass  # not yet implemented


@router.post(
    "/{id}/resend-invitation",
    dependencies=[Depends(authentication_required)],
    response_model=UserRead,
)
async def resend_user_invitation(id: str):  # pragma: no cover
    pass  # not yet implemented


@router.get("/{id}", response_model=UserRead)
async def get_user_by_id(id: str, token: str | None = None):  # pragma: no cover
    # if token is provided no authentication is needed but
    # an AccountOperator in status invited must exist with
    # user id and token and the token must not be expired
    pass  # not yet implemented


@router.post(
    "/{id}/accept-invitation",
    response_model=UserRead,
)
async def accept_user_invitation(
    id: UserId,
    data: UserAcceptInvitation,
    db_session: DBSession,
    db_engine: DBEngine,
):
    user_handler = UserHandler(db_session)
    accountuser_handler = AccountUserHandler(db_session)
    user = None
    account_user = None
    try:
        user = await user_handler.get(
            id=id, extra_conditions=[User.status.in_([UserStatus.DRAFT, UserStatus.ACTIVE])]
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    account_user = await accountuser_handler.first(
        AccountUser.user == user,
        AccountUser.invitation_token == data.invitation_token,
        AccountUser.status != AccountUserStatus.DELETED,
    )
    if not account_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation not found.",
        )

    if account_user.invitation_token_expires_at < datetime.now(UTC):  # type: ignore
        if account_user.status != AccountUserStatus.INVITATION_EXPIRED:
            await accountuser_handler.update(
                account_user, {"status": AccountUserStatus.INVITATION_EXPIRED}
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired.",
        )
    if account_user.account.status != AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Account related to this invitation is not Active.",
        )

    if user.status == UserStatus.DRAFT:
        if not data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required for Draft users.",
            )
    else:
        if data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A password cannot be provided for an Active User.",
            )
    async with get_tx_db_session(db_engine) as tx_session:
        if user.status == UserStatus.DRAFT:
            user_handler = UserHandler(tx_session)
            user = await user_handler.update(
                user.id,
                {
                    "password": pbkdf2_sha256.hash(data.password.get_secret_value()),  # type: ignore
                    "status": UserStatus.ACTIVE,
                    "last_used_account_id": account_user.account.id,
                },
            )
        else:
            user = await user_handler.get(user.id)
        accountuser_handler = AccountUserHandler(tx_session)
        account_user = await accountuser_handler.update(
            account_user.id,
            {
                "status": AccountUserStatus.ACTIVE,
                "joined_at": datetime.now(UTC),
                "invitation_token": None,
                "invitation_token_expires_at": None,
            },
        )
        return from_orm(UserRead, user)


@router.post("/{id}/reset-password", response_model=UserRead)
async def reset_user_password(id: str, data: UserResetPassword):  # pragma: no cover
    pass  # not yet implemented
