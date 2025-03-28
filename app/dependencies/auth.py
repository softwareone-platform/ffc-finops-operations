from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.auth import JWTBearer, JWTCredentials
from app.auth.constants import JWT_ALGORITHM, JWT_LEEWAY, UNAUTHORIZED_EXCEPTION
from app.auth.context import AuthenticationContext, auth_context
from app.conf import Settings
from app.db import handlers, models
from app.dependencies.core import AppSettings
from app.dependencies.db import DBSession


async def get_authentication_context(
    settings: AppSettings,
    db_session: DBSession,
    credentials: Annotated[JWTCredentials | None, Depends(JWTBearer())],
):
    """
    This function gets the authentication context from a JWT bearer token.
    It manages System and User actors and return the related authentication context.
    If no  credentials are provided, it returns a default unauthenticated context.

    """
    if credentials:
        actor_id = credentials.claim["sub"]
        try:
            if actor_id.startswith(models.System.PK_PREFIX):
                context = await get_authentication_context_for_system(
                    db_session=db_session, credentials=credentials, system_id=actor_id
                )
            else:
                context = await get_authentication_context_for_account_user(
                    settings=settings,
                    db_session=db_session,
                    credentials=credentials,
                    user_id=actor_id,
                )
        except (jwt.InvalidTokenError, handlers.DatabaseError) as e:
            raise UNAUTHORIZED_EXCEPTION from e

        reset_token = auth_context.set(context)

        try:
            yield context
            return
        finally:
            auth_context.reset(reset_token)
    yield


async def get_authentication_context_for_account_user(
    settings: Settings,
    db_session: AsyncSession,
    credentials: JWTCredentials,
    user_id: str,
) -> AuthenticationContext:
    """
    This functions retrieves the authentication context from a specific account user
    identified by a JWT bearer token.
    """

    user_handler = handlers.UserHandler(db_session)
    account_user_handler = handlers.AccountUserHandler(db_session)
    account_handler = handlers.AccountHandler(db_session)
    jwt.decode(
        credentials.credentials,
        settings.auth_access_jwt_secret,
        options={"require": ["exp", "nbf", "iat", "sub"]},
        algorithms=[JWT_ALGORITHM],
        leeway=JWT_LEEWAY,
    )
    user = await user_handler.get(
        user_id,
        extra_conditions=[models.User.status == models.UserStatus.ACTIVE],
    )
    account_id = credentials.claim.get("account_id", user.last_used_account_id)
    account = await account_handler.get(
        account_id,
        extra_conditions=[models.Account.status == models.AccountStatus.ACTIVE],
    )
    account_user = await account_user_handler.get_account_user(
        account_id=account_id,
        user_id=user_id,
        extra_conditions=[models.AccountUser.status == models.AccountUserStatus.ACTIVE],
    )
    if not account_user:
        raise UNAUTHORIZED_EXCEPTION
    context = AuthenticationContext(
        account=account,
        actor_type=models.ActorType.USER,
        user=user,
    )
    return context


async def get_authentication_context_for_system(
    db_session: AsyncSession,
    credentials: JWTCredentials,
    system_id: str,
) -> AuthenticationContext:
    """
    This functions retrieves the authentication context from a specific system account
    identified by a JWT bearer token.
    """
    system_handler = handlers.SystemHandler(db_session)

    system = await system_handler.get(
        system_id,
        [models.System.status == models.SystemStatus.ACTIVE],
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
        actor_type=models.ActorType.SYSTEM,
        system=system,
    )
    return context


async def authentication_required(
    settings: AppSettings,
    db_session: DBSession,
    credentials: Annotated[JWTCredentials | None, Depends(JWTBearer())],
) -> AsyncGenerator[None]:
    async with asynccontextmanager(get_authentication_context)(
        settings, db_session, credentials
    ) as auth_context:
        if not auth_context:
            raise UNAUTHORIZED_EXCEPTION
        yield


def check_operations_account(
    context: Annotated[AuthenticationContext | None, Depends(get_authentication_context)],
) -> None:
    """
    This function ensures that the account type is of type OPERATIONS
    """
    if not context:
        raise UNAUTHORIZED_EXCEPTION

    if context.account.type != models.AccountType.OPERATIONS:
        # This API can only be consumed in the context of an Operations Account
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You've found the door, but you don't have the key.",
        )
    return None


CurrentAuthContext = Annotated[AuthenticationContext | None, Depends(get_authentication_context)]
