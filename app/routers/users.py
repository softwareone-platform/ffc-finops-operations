from __future__ import annotations

import logging
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination import create_page, resolve_params
from sqlalchemy import ColumnExpressionArgument, and_
from sqlalchemy.orm import joinedload, with_loader_criteria

from app.auth.auth import authentication_required, check_operations_account
from app.auth.constants import UNAUTHORIZED_EXCEPTION
from app.conf import AppSettings
from app.db import DBEngine, DBSession, get_tx_db_session
from app.db.handlers import AccountHandler, AccountUserHandler, NotFoundError, UserHandler
from app.db.models import Account, AccountUser, User
from app.dependencies import (
    AccountId,
    AccountRepository,
    AccountUserRepository,
    CurrentAuthContext,
    UserId,
    UserRepository,
)
from app.enums import AccountStatus, AccountType, AccountUserStatus, UserStatus
from app.hasher import pbkdf2_sha256
from app.pagination import LimitOffsetPage, LimitOffsetParams, paginate
from app.schemas.core import AuditEventsSchema, convert_model_to_schema, extract_events
from app.schemas.users import (
    AccountForUser,
    AccountUserCreate,
    AccountUserRead,
    AccountUserReference,
    UserAcceptInvitation,
    UserInvitationRead,
    UserRead,
    UserReference,
    UserResetPassword,
    UserUpdate,
)
from app.utils import wrap_exc_in_http_response

logger = logging.getLogger(__name__)


async def fetch_user_or_404(
    id: UserId,
    auth_context: CurrentAuthContext,
    user_repo: UserRepository,
) -> User:
    """
    If called with an Affiliate Account it will return a 404 error if the
    given user ID has been deleted
    If called with an Operations Account it will return the user with the provided id
    """

    with wrap_exc_in_http_response(NotFoundError, status_code=status.HTTP_404_NOT_FOUND):
        extra_conditions: list[ColumnExpressionArgument] = []

        if (
            auth_context is not None
            and auth_context.account is not None
            and auth_context.account.type == AccountType.AFFILIATE
        ):
            extra_conditions.append(User.status != UserStatus.DELETED)

        return await user_repo.get(id=id, extra_conditions=extra_conditions)


# ======
# Routes
# ======

router = APIRouter()


@router.get(
    "",
    dependencies=[Depends(authentication_required)],
    response_model=LimitOffsetPage[UserRead],
)
async def get_users(user_repo: UserRepository, auth_context: CurrentAuthContext):
    """
    This endpoint returns all the users in the DB
    There are 2 possible scenarios

    1. Authentication is provided, and the Account is OPERATIONS. In this case, the query will
    be run and return all the users in the DB
    2. Authentication is provided, and the Account is AFFILIATE. In this case, the query is run only
    if the Account User status is not DELETED and the users belong to the authenticated account
     if the account is affiliated, the query will return all the users in the DB that
     satisfie the condition that the User's account is the same as the authenticated account
     and the account's status is not DELETED.


    """
    if auth_context.account.type == AccountType.OPERATIONS:  # type: ignore
        return await paginate(user_repo, UserRead)
    else:
        return await paginate(
            user_repo,
            UserRead,
            extra_conditions=[
                User.accounts.any(
                    and_(
                        AccountUser.account_id == auth_context.account.id,  # type: ignore
                        AccountUser.status != AccountUserStatus.DELETED,
                    ),
                ),
            ],
            page_options=[
                joinedload(User.accounts, innerjoin=True),
                with_loader_criteria(
                    AccountUser,
                    and_(
                        AccountUser.account_id == auth_context.account.id,  # type: ignore
                        AccountUser.status != AccountUserStatus.DELETED,
                    ),
                ),
            ],
        )


@router.post(
    "",
    dependencies=[Depends(authentication_required)],
    response_model=UserInvitationRead,
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

        response = convert_model_to_schema(
            UserInvitationRead,
            user,
            account_user=convert_model_to_schema(AccountUserRead, account_user),
        )
        return response


@router.put(
    "/{id}",
    dependencies=[Depends(authentication_required)],
    response_model=UserRead,
)
async def update_user(
    data: UserUpdate,
    user_repo: UserRepository,
    user: Annotated[User, Depends(fetch_user_or_404)],
):
    """
    This endpoint updates the name field of a user.
    Only the name can be updated.
    """
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user cannot be updated.",
        )
    to_update = data.model_dump(exclude_unset=True)
    db_user = await user_repo.update(user.id, data=to_update)
    return convert_model_to_schema(UserRead, db_user)


@router.delete(
    "/{id}",
    dependencies=[Depends(check_operations_account)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(
    auth_context: CurrentAuthContext,
    user: Annotated[User, Depends(fetch_user_or_404)],
    accountuser_repo: AccountUserRepository,
    user_repo: UserRepository,
):
    """
    This endpoint allows an OPERATOR to delete a user.
    A user cannot delete itself.
    """
    if user == auth_context.user:  #  type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user cannot delete itself.",
        )
    if user.status == UserStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user has already been deleted.",
        )
    account_users = await accountuser_repo.filter(
        AccountUser.status != AccountUserStatus.DELETED, AccountUser.user_id == user.id
    )
    await user_repo.soft_delete(id_or_obj=user.id)
    logger.info(f"The user {user.id} has been deleted.")
    for accountuser in account_users:
        await accountuser_repo.soft_delete(id_or_obj=accountuser.id)
    logger.info("All the account users have been deleted.")


@router.get(
    "/{id}/accounts",
    dependencies=[Depends(authentication_required)],
    response_model=LimitOffsetPage[AccountForUser],
)
async def get_user_accounts(
    user: Annotated[User, Depends(fetch_user_or_404)],
    account_repo: AccountRepository,
    auth_ctx: CurrentAuthContext,
):
    extra_conditions: list[ColumnExpressionArgument] = [
        Account.users.any(AccountUser.user == user),
    ]
    if auth_ctx is not None and auth_ctx.account.type == AccountType.AFFILIATE:
        extra_conditions.append(
            Account.users.any(AccountUser.status != AccountUserStatus.DELETED),
        )

    params: LimitOffsetParams = resolve_params()
    total = await account_repo.count(*extra_conditions)

    items: Sequence[Account] = []
    if params.limit > 0:
        items = await account_repo.fetch_page(
            limit=params.limit,
            offset=params.offset,
            extra_conditions=extra_conditions,
            options=[joinedload(Account.users)],
        )

    pages: list[AccountForUser] = []
    for account in items:
        if len(account.users) != 1:
            raise RuntimeError("invalid branch")

        account_user = account.users[0]
        page = AccountForUser(
            id=account.id,
            name=account.name,
            type=account.type,
            status=account.status,
            external_id=account.external_id,
            user=convert_model_to_schema(UserReference, account_user.user),
            account_user=convert_model_to_schema(AccountUserReference, account_user),
            events=extract_events(account, AuditEventsSchema),
        )

        pages.append(page)

    return create_page(pages, params=params, total=total)


@router.post(
    "/{id}/disable",
    dependencies=[Depends(check_operations_account)],
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
)
async def disable_user(
    user_repo: UserRepository,
    auth_context: CurrentAuthContext,
    user: Annotated[User, Depends(fetch_user_or_404)],
):
    """
    This endpoint allows an OPERATOR to disable a user.
    A user cannot disable itself.
    """

    if user == auth_context.user:  #  type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user cannot disable itself.",
        )
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"User's status is '{user.status._value_}' only active users can be disabled."),
        )
    user = await user_repo.update(id_or_obj=user.id, data={"status": UserStatus.DISABLED})
    return convert_model_to_schema(UserRead, user)


@router.post(
    "/{id}/enable",
    dependencies=[Depends(check_operations_account)],
    response_model=UserRead,
)
async def enable_user(
    user_repo: UserRepository,
    auth_context: CurrentAuthContext,
    user: Annotated[User, Depends(fetch_user_or_404)],
):
    """
    This endpoint allows an OPERATOR to enable a user.
    A user cannot enable itself.
    """
    if user == auth_context.user:  #  type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user cannot enable itself.",
        )
    if user.status != UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User's status is '{user.status._value_}' only disabled users can be enabled."
            ),
        )
    user = await user_repo.update(id_or_obj=user.id, data={"status": UserStatus.ACTIVE})
    return convert_model_to_schema(UserRead, user)


@router.post(
    "/{id}/accounts/{account_id}/resend-invitation",
    dependencies=[Depends(authentication_required)],
    response_model=UserInvitationRead,
)
async def resend_user_invitation(
    settings: AppSettings,
    auth_context: CurrentAuthContext,
    user: Annotated[User, Depends(fetch_user_or_404)],
    account_id: AccountId,
    account_repository: AccountRepository,
    accountuser_repository: AccountUserRepository,
):
    if user.status == UserStatus.DELETED:
        status_code = status.HTTP_404_NOT_FOUND
        detail = f"User with ID `{user.id}` wasn't found."

        if auth_context.account.type == AccountType.OPERATIONS:  # type: ignore
            status_code = status.HTTP_400_BAD_REQUEST
            detail = f"Cannot resend invitation: user with ID `{user.id}` is deleted."

        raise HTTPException(status_code=status_code, detail=detail)

    account = await account_repository.first(
        Account.id == account_id, Account.status != AccountStatus.DELETED
    )

    if not account or (
        auth_context.account.type == AccountType.AFFILIATE and auth_context.account != account  # type: ignore
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID `{account_id}` wasn't found.",
        )

    account_user = await accountuser_repository.get_account_user(
        account_id=account.id,
        user_id=user.id,
        extra_conditions=[AccountUser.status != AccountUserStatus.DELETED],
    )
    if not account_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No invitation to Account with ID `{account_id}` "
                f"was found for User with ID `{user.id}."
            ),
        )
    if account_user.status == AccountUserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with ID `{user.id}` already belong to the Account with ID `{user.id}.",
        )

    account_user.status = AccountUserStatus.INVITED
    account_user.invitation_token = secrets.token_urlsafe(settings.invitation_token_length)
    account_user.invitation_token_expires_at = datetime.now(UTC) + timedelta(
        days=settings.invitation_token_expires_days
    )
    account_user = await accountuser_repository.update(account_user)
    response = convert_model_to_schema(
        UserInvitationRead,
        user,
        account_user=convert_model_to_schema(AccountUserRead, account_user),
    )
    return response


@router.get("/{id}", response_model=UserRead)
async def get_user_by_id(
    id: str,
    auth_context: CurrentAuthContext,
    accountuser_repo: AccountUserRepository,
    user_repo: UserRepository,
    token: str | None = None,
):
    """
        This endpoint returns the user filtered by the given ID.
    There are 3 possible scenarios
    1. No Authentication is provided, but an invitation token is sent with the request.
       In this case, if the invitation token is valid and the user exists, its record will
       be returned.
    2. Authentication is provided, and the Account is OPERATIONS. In this case, the query will
    be run with no more checks
    3. Authentication is provided, and the Account is AFFILIATE. In this case, the query is run only
    if the Account User status is not DELETED.

    Raises:
        - HTTPException with status 404 if no account user is found
        - HTTPException 401 if the invitation token is not valid


    """
    user_id = id
    response = None
    if auth_context is None:
        # No Authentication. We must verify the invitation token
        invitation_token = token
        account_user = await accountuser_repo.first(
            AccountUser.invitation_token == invitation_token,
            AccountUser.status.in_(
                [AccountUserStatus.INVITED, AccountUserStatus.INVITATION_EXPIRED]
            ),
        )
        if account_user is None:
            logger.error(f"Invalid invitation token for User with ID `{user_id}`.")
            raise UNAUTHORIZED_EXCEPTION
        response = await user_repo.get(id=user_id)
    elif auth_context.account.type == AccountType.OPERATIONS:
        with wrap_exc_in_http_response(NotFoundError, status_code=status.HTTP_404_NOT_FOUND):
            response = await user_repo.get(id=user_id)
    elif auth_context.account.type == AccountType.AFFILIATE:
        account_user = await accountuser_repo.get_account_user(
            account_id=auth_context.account.id,
            user_id=user_id,
            extra_conditions=[AccountUser.status != AccountUserStatus.DELETED],
        )
        if account_user is None:
            logger.error(f"User with ID `{user_id}` wasn't found.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID `{user_id}` wasn't found.",
            )
        with wrap_exc_in_http_response(NotFoundError, status_code=status.HTTP_404_NOT_FOUND):
            # not filtering [AccountUser.status != AccountUserStatus.DELETED]
            # because if the user is in
            # status DELETE then the account user will be deleted as well
            response = await user_repo.get(id=user_id)
    return convert_model_to_schema(UserRead, response)


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
        return convert_model_to_schema(UserRead, user)


@router.post("/{id}/reset-password", response_model=UserRead)
async def reset_user_password(
    id: UserId,
    user_repo: UserRepository,
    data: UserResetPassword,
):
    user = None
    with wrap_exc_in_http_response(
        NotFoundError,
        status_code=status.HTTP_400_BAD_REQUEST,
        error_msg="You have summoned the mighty Error 400! It demands a better request.",
    ):
        user = await user_repo.get(
            id,
            extra_conditions=[
                User.status == UserStatus.ACTIVE,
                User.pwd_reset_token == data.pwd_reset_token,
                User.pwd_reset_token.isnot(None),
                User.pwd_reset_token_expires_at.isnot(None),
            ],
        )

    if user.pwd_reset_token_expires_at < datetime.now(UTC):  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Your password reset token has expired."
        )
    if not data.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is required.",
        )
    user = await user_repo.update(
        user.id,
        {
            "password": pbkdf2_sha256.hash(data.password.get_secret_value()),  # type: ignore
        },
    )

    return convert_model_to_schema(UserRead, user)
