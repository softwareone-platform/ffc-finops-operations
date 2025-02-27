from contextlib import asynccontextmanager
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.constants import JWT_ALGORITHM, JWT_LEEWAY, UNAUTHORIZED_EXCEPTION
from app.auth.context import AuthenticationContext, auth_context
from app.conf import AppSettings
from app.db import DBSession
from app.db.handlers import (
    AccountHandler,
    AccountUserHandler,
    DatabaseError,
    SystemHandler,
    UserHandler,
)
from app.db.models import Account, AccountUser, System, User
from app.enums import (
    AccountStatus,
    AccountType,
    AccountUserStatus,
    ActorType,
    SystemStatus,
    UserStatus,
)


class JWTCredentials(HTTPAuthorizationCredentials):
    claim: dict[str, Any]


class JWTBearer(HTTPBearer):
    def __init__(self):
        super().__init__(auto_error=False)

    async def __call__(self, request: Request) -> JWTCredentials | None:
        credentials = await super().__call__(request)
        if credentials:
            try:
                return JWTCredentials(
                    scheme=credentials.scheme,
                    credentials=credentials.credentials,
                    claim=jwt.decode(
                        credentials.credentials,
                        "",
                        options={"verify_signature": False},
                        algorithms=[JWT_ALGORITHM],
                    ),
                )
            except jwt.InvalidTokenError:
                raise UNAUTHORIZED_EXCEPTION


async def get_authentication_context(
    settings: AppSettings,
    db_session: DBSession,
    credentials: Annotated[JWTCredentials | None, Depends(JWTBearer())],
):
    if credentials:
        # system_handler = SystemHandler(db_session)
        # user_handler = UserHandler(db_session)
        # account_user_handler = AccountUserHandler(db_session)
        # account_handler = AccountHandler(db_session)

        actor_id = credentials.claim["sub"]
        try:
            if actor_id.startswith(System.PK_PREFIX):
                context = await get_authentication_context_for_system(
                    actor_id, credentials, db_session
                )
            else:
                context = await get_authentication_context_for_account_user(
                    actor_id, credentials, settings, db_session
                )
        except (jwt.InvalidTokenError, DatabaseError) as e:
            raise UNAUTHORIZED_EXCEPTION from e

        reset_token = auth_context.set(context)

        try:
            yield context
            return
        finally:
            auth_context.reset(reset_token)
    yield


async def get_authentication_context_for_account_user(actor_id, credentials, settings, db_session):
    user_handler = UserHandler(db_session)
    account_user_handler = AccountUserHandler(db_session)
    account_handler = AccountHandler(db_session)
    jwt.decode(
        credentials.credentials,
        settings.auth_access_jwt_secret,
        options={"require": ["exp", "nbf", "iat", "sub"]},
        algorithms=[JWT_ALGORITHM],
        leeway=JWT_LEEWAY,
    )
    user = await user_handler.get(
        actor_id,
        extra_conditions=[User.status == UserStatus.ACTIVE],
    )
    account_id = credentials.claim.get("account_id", user.last_used_account_id)
    account = await account_handler.get(
        account_id,
        extra_conditions=[Account.status == AccountStatus.ACTIVE],
    )
    account_user = await account_user_handler.get_account_user(
        account_id=account_id,
        user_id=actor_id,
        extra_conditions=[AccountUser.status == AccountUserStatus.ACTIVE],
    )
    if not account_user:
        raise UNAUTHORIZED_EXCEPTION
    context = AuthenticationContext(
        account=account,
        actor_type=ActorType.USER,
        user=user,
    )
    return context


async def get_authentication_context_for_system(
    actor_id: str, credentials: JWTCredentials, db_session: DBSession
) -> AuthenticationContext:
    system_handler = SystemHandler(db_session)

    system = await system_handler.get(
        actor_id,
        [System.status == SystemStatus.ACTIVE],
    )
    jwt.decode(
        credentials.credentials,
        system.jwt_secret,
        options={"require": ["exp", "nbf", "iat", "sub"]},
        algorithms=[JWT_ALGORITHM],
        leeway=JWT_LEEWAY,
    )
    # TODO check maximum allowed lifespan
    context = AuthenticationContext(
        account=system.owner,
        actor_type=ActorType.SYSTEM,
        system=system,
    )
    return context


async def authentication_required(
    settings: AppSettings,
    db_session: DBSession,
    credentials: Annotated[JWTCredentials | None, Depends(JWTBearer())],
):
    async with asynccontextmanager(get_authentication_context)(
        settings, db_session, credentials
    ) as auth_context:
        if not auth_context:
            raise UNAUTHORIZED_EXCEPTION
        yield


def check_operations_account(
    context: Annotated[AuthenticationContext | None, Depends(get_authentication_context)],
):
    """
    This function ensures that the account type is of type OPERATIONS
    """
    if not context:
        raise UNAUTHORIZED_EXCEPTION

    if context.account.type != AccountType.OPERATIONS:
        # This API can only be consumed in the context of an Operations Account
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You've found the door, but you don't have the key.",
        )
