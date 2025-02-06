from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.auth.auth import JWTBearer, JWTCredentials, get_authentication_context
from app.auth.context import AuthenticationContext, auth_context
from app.db.models import System, User
from app.enums import AccountUserStatus, ActorType, SystemStatus, UserStatus
from tests.conftest import JWTTokenFactory, ModelFactory
from tests.pytest_plugins.capsql.capturer import SQLAlchemyCapturer


async def test_jwt_bearer(mocker: MockerFixture, jwt_token_factory: JWTTokenFactory):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token_factory('test', 'secret')}"}
    credentials = await bearer(request)
    assert credentials is not None
    assert isinstance(credentials, JWTCredentials)
    assert credentials.claim["sub"] == "test"


async def test_jwt_bearer_invalid_token(mocker: MockerFixture):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": "Bearer 1234567890"}
    with pytest.raises(HTTPException) as exc_info:
        await bearer(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


async def test_jwt_bearer_no_token(mocker: MockerFixture):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        await bearer(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


async def test_get_authentication_context_system(
    mocker: MockerFixture,
    gcp_jwt_token: str,
    gcp_extension: System,
    db_session: AsyncSession,
    capsql: SQLAlchemyCapturer,
):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {gcp_jwt_token}"}
    credentials = await bearer(request)

    with pytest.raises(LookupError):
        auth_context.get()

    with capsql:
        async with asynccontextmanager(get_authentication_context)(
            db_session, credentials
        ) as context:
            assert isinstance(context, AuthenticationContext)
            assert context.actor_type == ActorType.SYSTEM
            assert context.system == gcp_extension
            assert context.user is None
            assert context.account == gcp_extension.owner
            assert context.get_actor() == gcp_extension
            assert auth_context.get() == context

        capsql.assert_query_count(1)

    with pytest.raises(LookupError):
        auth_context.get()


@pytest.mark.parametrize(
    "system_status",
    [SystemStatus.DELETED, SystemStatus.DISABLED],
)
async def test_get_authentication_context_system_not_active(
    mocker: MockerFixture,
    system_factory: ModelFactory[System],
    jwt_token_factory: JWTTokenFactory,
    db_session: AsyncSession,
    system_status: SystemStatus,
):
    system = await system_factory(
        status=system_status,
        jwt_secret="secret",
    )
    jwt_token = jwt_token_factory(system.id, "secret")
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token}"}
    credentials = await bearer(request)

    with pytest.raises(HTTPException) as exc_info:
        async with asynccontextmanager(get_authentication_context)(db_session, credentials):
            pass

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"

    with pytest.raises(LookupError):
        auth_context.get()


@pytest.mark.parametrize(
    "user_status",
    [UserStatus.DELETED, UserStatus.DISABLED, UserStatus.DRAFT],
)
async def test_get_authentication_context_user_invalid_status(
    mocker: MockerFixture,
    user_factory: ModelFactory[User],
    jwt_token_factory: JWTTokenFactory,
    db_session: AsyncSession,
    user_status: UserStatus,
):
    user = await user_factory(status=user_status)
    jwt_token = jwt_token_factory(user.id, settings.auth_jwt_secret)

    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token}"}
    credentials = await bearer(request)

    with pytest.raises(HTTPException) as exc_info:
        async with asynccontextmanager(get_authentication_context)(db_session, credentials):
            pass

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"

    with pytest.raises(LookupError):
        auth_context.get()


@pytest.mark.parametrize(
    "accountuser_status",
    [
        AccountUserStatus.DELETED,
        AccountUserStatus.INVITATION_EXPIRED,
        AccountUserStatus.INVITED,
    ],
)
async def test_get_authentication_context_user_invalid_accountuser_status(
    mocker: MockerFixture,
    user_factory: ModelFactory[User],
    jwt_token_factory: JWTTokenFactory,
    db_session: AsyncSession,
    accountuser_status: AccountUserStatus,
):
    user = await user_factory(accountuser_status=accountuser_status)
    jwt_token = jwt_token_factory(user.id, settings.auth_jwt_secret)

    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token}"}
    credentials = await bearer(request)

    with pytest.raises(HTTPException) as exc_info:
        async with asynccontextmanager(get_authentication_context)(db_session, credentials):
            pass

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"

    with pytest.raises(LookupError):
        auth_context.get()


async def test_get_authentication_context_user_account_does_not_exist(
    mocker: MockerFixture,
    user_factory: ModelFactory[User],
    jwt_token_factory: JWTTokenFactory,
    db_session: AsyncSession,
):
    user = await user_factory()
    jwt_token = jwt_token_factory(user.id, settings.auth_jwt_secret, account_id="FACC-0000-0000")

    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token}"}
    credentials = await bearer(request)

    with pytest.raises(HTTPException) as exc_info:
        async with asynccontextmanager(get_authentication_context)(db_session, credentials):
            pass

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"

    with pytest.raises(LookupError):
        auth_context.get()
