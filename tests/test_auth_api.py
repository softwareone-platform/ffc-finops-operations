from datetime import UTC, datetime, timedelta

import jwt
import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import JWT_ALGORITHM
from app.conf import Settings
from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountUserStatus, UserStatus
from tests.types import ModelFactory


@freeze_time("2024-01-01T00:00:00Z")
async def test_get_tokens_from_credentials(
    db_session: AsyncSession,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    test_settings: Settings,
):
    user = await user_factory(password="ThisIsOk123$")
    assert user.last_login_at is None
    account = await db_session.get(Account, user.last_used_account_id)
    payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
    }
    response = await api_client.post("/auth/tokens", json=payload)
    assert response.status_code == 200
    data = response.json()

    await db_session.refresh(user)
    assert user.last_login_at == datetime.now(UTC)

    assert data["user"]["id"] == user.id
    assert data["user"]["name"] == user.name
    assert data["user"]["email"] == user.email
    assert data["account"]["id"] == account.id  # type: ignore
    assert data["account"]["name"] == account.name  # type: ignore
    access_token = jwt.decode(
        data["access_token"],
        test_settings.auth_access_jwt_secret,
        options={"require": ["exp", "nbf", "iat", "sub"]},
        algorithms=[JWT_ALGORITHM],
    )
    timestamp = int(datetime.now(UTC).timestamp())
    assert access_token["sub"] == user.id
    assert access_token["account_id"] == account.id  # type: ignore
    assert access_token["iat"] == access_token["nbf"] == timestamp
    assert access_token["exp"] == timestamp + test_settings.auth_access_jwt_lifespan_minutes * 60

    refresh_token = jwt.decode(
        data["refresh_token"],
        test_settings.auth_refresh_jwt_secret,
        options={"require": ["exp", "nbf", "iat", "sub"]},
        algorithms=[JWT_ALGORITHM],
    )
    timestamp = int(datetime.now(UTC).timestamp())
    assert refresh_token["sub"] == user.id
    assert "account_id" not in refresh_token
    assert refresh_token["iat"] == refresh_token["nbf"] == timestamp
    lifespan_sec = test_settings.auth_refresh_jwt_lifespan_days * 60 * 60 * 24
    assert refresh_token["exp"] == timestamp + lifespan_sec


@pytest.mark.parametrize(
    "user_status",
    [UserStatus.DRAFT, UserStatus.DELETED, UserStatus.DISABLED],
)
async def test_get_tokens_from_credentials_user_not_active(
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    user_status: UserStatus,
):
    user = await user_factory(
        password="ThisIsOk123$",
        status=user_status,
    )
    payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
    }
    response = await api_client.post("/auth/tokens", json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.DELETED, AccountStatus.DISABLED],
)
async def test_get_tokens_from_credentials_account_not_active(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    account_status: AccountStatus,
):
    user = await user_factory(
        password="ThisIsOk123$",
    )
    account = await account_factory(status=account_status)
    await accountuser_factory(user_id=user.id, account_id=account.id)
    payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "accountuser_status",
    [AccountUserStatus.DELETED, AccountUserStatus.INVITATION_EXPIRED, AccountUserStatus.INVITED],
)
async def test_get_tokens_from_credentials_accountuser_not_active(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    accountuser_status: AccountStatus,
):
    user = await user_factory(
        password="ThisIsOk123$",
    )
    account = await account_factory()
    await accountuser_factory(user_id=user.id, account_id=account.id, status=accountuser_status)
    payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=payload)
    assert response.status_code == 401


async def test_get_tokens_from_credentials_invalid_password(
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
):
    user = await user_factory(password="ThisIsOk123$")

    payload = {
        "email": user.email,
        "password": "OtherPwd2443",
    }
    response = await api_client.post("/auth/tokens", json=payload)

    assert response.status_code == 401


async def test_get_tokens_from_credentials_invalid_user(
    api_client: AsyncClient,
):
    payload = {
        "email": "does.not@exists.err",
        "password": "OtherPwd2443",
    }
    response = await api_client.post("/auth/tokens", json=payload)

    assert response.status_code == 401


@freeze_time("2024-01-01T00:00:00Z")
async def test_get_tokens_from_credentials_no_account_user(
    db_session: AsyncSession,
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account")
    account_not_bounded = await account_factory(name="Another not bounded")
    await accountuser_factory(user.id, account.id)
    payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
        "account": {"id": account_not_bounded.id},
    }
    response = await api_client.post("/auth/tokens", json=payload)
    assert response.status_code == 401


async def test_get_tokens_from_refresh(
    db_session: AsyncSession,
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account")
    await accountuser_factory(user.id, account.id)
    login_payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
    }
    response = await api_client.post("/auth/tokens", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert user.last_used_account_id != account.id
    refresh_token = data["refresh_token"]
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 200
    data = response.json()

    await db_session.refresh(user)
    assert user.last_used_account_id == account.id

    assert data["user"]["id"] == user.id
    assert data["user"]["name"] == user.name
    assert data["user"]["email"] == user.email
    assert data["account"]["id"] == account.id
    assert data["account"]["name"] == account.name
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None


async def test_get_tokens_from_refresh_no_account_user(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[Account],
    api_client: AsyncClient,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account")
    account_not_bounded = await account_factory(name="Another not bounded")
    await accountuser_factory(user.id, account.id)
    login_payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
    }
    response = await api_client.post("/auth/tokens", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert user.last_used_account_id != account.id
    refresh_token = data["refresh_token"]
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account_not_bounded.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401
    data = response.json()


async def test_get_tokens_from_refresh_account_not_found(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[Account],
    api_client: AsyncClient,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account")
    await accountuser_factory(user.id, account.id)
    login_payload = {
        "email": user.email,
        "password": "ThisIsOk123$",
    }
    response = await api_client.post("/auth/tokens", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert user.last_used_account_id != account.id
    refresh_token = data["refresh_token"]
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": "does-not-exist"},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401
    data = response.json()


async def test_get_tokens_from_refresh_invalid_token(
    account_factory: ModelFactory[Account],
    api_client: AsyncClient,
):
    account = await account_factory()
    refresh_token = "whatever"
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401


async def test_get_tokens_from_refresh_expired(
    db_session: AsyncSession,
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[Account],
    api_client: AsyncClient,
    test_settings: Settings,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account")
    await accountuser_factory(user.id, account.id)
    iat = nbf = datetime.now(UTC) - timedelta(days=test_settings.auth_refresh_jwt_lifespan_days + 2)
    refresh_token = jwt.encode(
        {
            "sub": user.id,
            "iat": iat,
            "nbf": nbf,
            "exp": nbf + timedelta(days=test_settings.auth_refresh_jwt_lifespan_days),
        },
        test_settings.auth_refresh_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "user_status",
    [UserStatus.DRAFT, UserStatus.DELETED, UserStatus.DISABLED],
)
async def test_get_tokens_from_refresh_user_not_active(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[Account],
    api_client: AsyncClient,
    user_status: UserStatus,
    test_settings: Settings,
):
    user = await user_factory(password="ThisIsOk123$", status=user_status)
    account = await account_factory(name="Another account")
    await accountuser_factory(user.id, account.id)
    iat = nbf = datetime.now(UTC)
    refresh_token = jwt.encode(
        {
            "sub": user.id,
            "iat": iat,
            "nbf": nbf,
            "exp": nbf + timedelta(days=test_settings.auth_refresh_jwt_lifespan_days),
        },
        test_settings.auth_refresh_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.DELETED, AccountStatus.DISABLED],
)
async def test_get_tokens_from_refresh_account_not_active(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[Account],
    api_client: AsyncClient,
    account_status: AccountStatus,
    test_settings: Settings,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account", status=account_status)
    await accountuser_factory(user.id, account.id)
    iat = nbf = datetime.now(UTC)
    refresh_token = jwt.encode(
        {
            "sub": user.id,
            "iat": iat,
            "nbf": nbf,
            "exp": nbf + timedelta(days=test_settings.auth_refresh_jwt_lifespan_days),
        },
        test_settings.auth_refresh_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "accountuser_status",
    [AccountUserStatus.DELETED, AccountUserStatus.INVITATION_EXPIRED, AccountUserStatus.INVITED],
)
async def test_get_tokens_from_refresh_accountuser_not_active(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[Account],
    api_client: AsyncClient,
    accountuser_status: AccountUserStatus,
    test_settings: Settings,
):
    user = await user_factory(password="ThisIsOk123$")
    account = await account_factory(name="Another account")
    await accountuser_factory(user.id, account.id, status=accountuser_status)
    iat = nbf = datetime.now(UTC)
    refresh_token = jwt.encode(
        {
            "sub": user.id,
            "iat": iat,
            "nbf": nbf,
            "exp": nbf + timedelta(days=test_settings.auth_refresh_jwt_lifespan_days),
        },
        test_settings.auth_refresh_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    refresh_payload = {
        "refresh_token": refresh_token,
        "account": {"id": account.id},
    }
    response = await api_client.post("/auth/tokens", json=refresh_payload)
    assert response.status_code == 401
