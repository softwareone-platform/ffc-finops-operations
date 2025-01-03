import uuid
from collections.abc import Callable

import pytest
from fastapi import HTTPException
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import JWTBearer, JWTCredentials, get_current_system
from app.db.handlers import SystemHandler
from app.db.models import System


async def test_jwt_bearer(mocker, jwt_token_factory):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token_factory('test', 'secret')}"}
    credentials = await bearer(request)
    assert credentials is not None
    assert isinstance(credentials, JWTCredentials)
    assert credentials.claim["sub"] == "test"


async def test_jwt_bearer_invalid_token(mocker):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": "Bearer 1234567890"}
    with pytest.raises(HTTPException) as exc_info:
        await bearer(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


async def test_jwt_bearer_no_token(mocker):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        await bearer(request)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


async def test_get_current_system(
    mocker: MockerFixture, gcp_jwt_token: str, gcp_extension: System, db_session: AsyncSession
):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {gcp_jwt_token}"}
    credentials = await bearer(request)
    handler = SystemHandler(db_session)
    system = await get_current_system(handler, credentials)
    assert system.id == gcp_extension.id


async def test_get_current_system_system_not_found(
    mocker: MockerFixture, jwt_token_factory: Callable[[str, str], str], db_session: AsyncSession
):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token_factory(str(uuid.uuid4()), 'secret')}"}
    credentials = await bearer(request)
    handler = SystemHandler(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_system(handler, credentials)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"


async def test_get_current_system_invalid_subject(
    mocker: MockerFixture, jwt_token_factory: Callable[[str, str], str], db_session: AsyncSession
):
    bearer = JWTBearer()
    request = mocker.Mock()
    request.headers = {"Authorization": f"Bearer {jwt_token_factory('test', 'secret')}"}
    credentials = await bearer(request)
    handler = SystemHandler(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_system(handler, credentials)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthorized"
