from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf import Settings
from app.db.handlers import NotFoundError
from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountUserStatus, UserStatus
from tests.types import JWTTokenFactory, ModelFactory

# -----------
# GET USER BY ID
# -----------


@pytest.mark.parametrize(
    "account_status",
    [
        AccountUserStatus.INVITED,
        AccountUserStatus.INVITATION_EXPIRED,
        AccountUserStatus.DELETED,
        AccountUserStatus.ACTIVE,
    ],
)
async def test_operations_account_can_always_get_user_by_id(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    gcp_account: Account,
    operations_client: AsyncClient,
    test_settings: Settings,
    account_status: str,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=gcp_account.id,
        status=account_status,
        invitation_token="my-amazing-invitation-token",
        invitation_token_expires_at=datetime.now(UTC)
        + timedelta(days=test_settings.invitation_token_expires_days),
    )

    response = await operations_client.get(f"/users/{user.id}")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data.get("name") == user.name
    assert data.get("email") == user.email
    assert data.get("id") == user.id


@pytest.mark.parametrize(
    ("account_status", "response_status"),
    [
        (AccountUserStatus.ACTIVE, 200),
        (AccountUserStatus.INVITED, 200),
        (AccountUserStatus.INVITATION_EXPIRED, 200),
        (AccountUserStatus.DELETED, 404),
    ],
)
async def test_affiliate_account_can_get_user_by_id_only_with_status_not_deleted(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    affiliate_client: AsyncClient,
    gcp_account: Account,
    test_settings: Settings,
    account_status: str,
    response_status: int,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=gcp_account.id,
        status=account_status,
        invitation_token="my-amazing-invitation-token",
        invitation_token_expires_at=datetime.now(UTC)
        + timedelta(days=test_settings.invitation_token_expires_days),
    )
    response = await affiliate_client.get(f"/users/{user.id}")
    assert response.status_code == response_status
    if response_status == 200:
        data = response.json()
        assert data is not None
        assert data.get("name") == user.name
        assert data.get("email") == user.email
        assert data.get("id") == user.id


async def test_cannot_get_user_by_id_with_affiliate_account_client_and_not_existing_user(
    affiliate_client: AsyncClient,
):
    response = await affiliate_client.get("/users/FUSR-8994-8942")
    assert response.status_code == 404


async def test_get_user_by_id_with_no_auth_and_invalid_invitation_token(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    gcp_account: Account,
    test_settings: Settings,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=gcp_account.id,
        status=AccountUserStatus.INVITED,
        invitation_token="my-amazing-invitation-token",
        invitation_token_expires_at=datetime.now(UTC)
        + timedelta(days=test_settings.invitation_token_expires_days),
    )
    response = await api_client.get(f"/users/{user.id}?token=what_a_wonderful_world")
    assert response.status_code == 401


async def test_get_user_by_id_with_no_auth_and_invitation_token(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    gcp_account: Account,
    test_settings: Settings,
):
    user = await user_factory(
        name="Invited User2",
        email="invite2d@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=gcp_account.id,
        status=AccountUserStatus.INVITED,
        invitation_token="my-amazing-invitation-token",
        invitation_token_expires_at=datetime.now(UTC)
        + timedelta(days=test_settings.invitation_token_expires_days),
    )
    response = await api_client.get(f"/users/{user.id}?token=my-amazing-invitation-token")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data.get("name") == user.name
    assert data.get("email") == user.email
    assert data.get("id") == user.id


async def test_get_user_by_id_exception():
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    mock_repo = MagicMock()
    mock_repo.session = mock_session
    mock_repo.model_cls = MagicMock(__name__="MockTest")

    mock_repo.get = AsyncMock(side_effect=NotFoundError("User with ID `123` wasn't found."))

    with pytest.raises(NotFoundError, match="User with ID `123` wasn't found."):
        await mock_repo.get(id="123")


# -------
# List  Users
# -------


@pytest.mark.parametrize(
    ("useraccount_status", "http_status"),
    [
        (AccountUserStatus.ACTIVE, 200),
        (AccountUserStatus.INVITED, 200),
        (AccountUserStatus.INVITATION_EXPIRED, 200),
        (AccountUserStatus.DELETED, 200),
    ],
)
async def test_operators_can_always_list_users(
    operations_client: AsyncClient,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
    useraccount_status: str,
    http_status: str,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=useraccount_status
    )

    response = await operations_client.get("/users")
    data = response.json()
    assert response.status_code == http_status
    assert isinstance(data.get("items"), list)


@pytest.mark.parametrize(
    ("user_status", "http_status"),
    [
        (AccountUserStatus.ACTIVE, 200),
        (AccountUserStatus.INVITED, 200),
        (AccountUserStatus.INVITATION_EXPIRED, 200),
        (AccountUserStatus.DELETED, 200),
    ],
)
async def test_affiliate_cannot_always_list_users(
    affiliate_client: AsyncClient,
    affiliate_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
    user_status: str,
    http_status: str,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(user_id=user.id, account_id=affiliate_account.id, status=user_status)

    response = await affiliate_client.get("/users")
    data = response.json()
    assert response.status_code == http_status
    assert isinstance(data.get("items"), list)


async def test_list_users_multiple_pages(
    operations_client: AsyncClient,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
    db_session: AsyncSession,
):
    users_ids = []
    for index in range(30):
        user = await user_factory(
            name=f"Peter Parker_{index}",
            email=f"peter.parker_{index}@spiderman.com",
            status=UserStatus.ACTIVE,
        )
        users_ids.append(user.id)

    for user_id in users_ids:
        await accountuser_factory(
            user_id=user_id, account_id=operations_account.id, status=AccountStatus.ACTIVE
        )

    first_page_response = await operations_client.get(
        "/users",
        params={"limit": 5},
    )
    first_page_data = first_page_response.json()
    assert first_page_response.status_code == 200
    assert first_page_data["total"] == 30
    assert len(first_page_data["items"]) == 5
    assert first_page_data["limit"] == 5
    assert first_page_data["offset"] == 0
    #
    second_page_response = await operations_client.get(
        "/users",
        params={"limit": 3, "offset": 5},
    )
    second_page_data = second_page_response.json()

    assert second_page_response.status_code == 200
    assert second_page_data["total"] == 30
    assert len(second_page_data["items"]) == 3
    assert second_page_data["limit"] == 3
    assert second_page_data["offset"] == 5

    third_page_response = await operations_client.get(
        "/users",
        params={"offset": 8},
    )
    third_page_data = third_page_response.json()

    assert third_page_response.status_code == 200
    assert third_page_data["total"] == 30
    assert len(third_page_data["items"]) == 22
    assert third_page_data["limit"] > 2
    assert third_page_data["offset"] == 8

    all_items = first_page_data["items"] + second_page_data["items"] + third_page_data["items"]
    assert len(all_items) == 30


async def test_list_users_with_deleted_account(
    affiliate_client: AsyncClient,
    gcp_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    await accountuser_factory(
        user_id=user.id, account_id=gcp_account.id, status=AccountUserStatus.DELETED
    )

    response = await affiliate_client.get("/users")
    assert response.status_code == 200
    page = response.json()
    items = page.get("items")
    assert isinstance(items, list)
    assert len(items) == 0


async def test_list_users_with_2_accounts(
    affiliate_client: AsyncClient,
    gcp_account: Account,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    user_2 = await user_factory(
        name="Jerry Drake",
        email="jerry.drake@misterno.com",
        status=UserStatus.ACTIVE,
    )
    account_user_1 = await accountuser_factory(
        user_id=user.id, account_id=gcp_account.id, status=AccountUserStatus.ACTIVE
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.DELETED
    )
    await accountuser_factory(
        user_id=user_2.id, account_id=operations_account.id, status=AccountUserStatus.INVITED
    )
    response = await affiliate_client.get("/users")
    assert response.status_code == 200
    page = response.json()
    items = page.get("items")
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    assert item.get("id") == user.id
    assert item.get("name") == user.name
    assert item.get("email") == user.email
    assert item.get("status") == user.status
    assert item["account_user"]["id"] == account_user_1.id  # account affiliate


##
# Disable User
##


async def test_operator_can_disable_active_user(
    operations_client: AsyncClient,
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await operations_client.post(f"/users/{user.id}/disable")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == UserStatus.DISABLED


async def test_operator_cannot_disable_not_active_user(
    operations_client: AsyncClient,
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.DELETED,
    )
    response = await operations_client.post(f"/users/{user.id}/disable")
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "User's status is 'deleted' only active users can be disabled."


async def test_operator_cannot_disable_itself(
    operations_account: Account,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    jwt_token_factory: JWTTokenFactory,
    test_settings: Settings,
    accountuser_factory: ModelFactory[AccountUser],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.ACTIVE
    )
    jwt_token = jwt_token_factory(
        user.id, test_settings.auth_access_jwt_secret, account_id=operations_account.id
    )

    response = await api_client.post(
        f"/users/{user.id}/disable",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "A user cannot disable itself."


@pytest.mark.parametrize(
    "user_status",
    [
        UserStatus.DELETED,
        UserStatus.ACTIVE,
        UserStatus.DISABLED,
        UserStatus.DRAFT,
    ],
)
async def test_affiliate_cannot_disable_user(
    affiliate_client: AsyncClient,
    user_factory: ModelFactory[User],
    user_status: str,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=user_status,
    )
    response = await affiliate_client.post(f"/users/{user.id}/disable")
    assert response.status_code == 403
    data = response.json()
    assert data["detail"] == "You've found the door, but you don't have the key."


##
# Update User
##


async def test_affiliate_can_update_user_name(
    affiliate_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await affiliate_client.put(
        f"/users/{user.id}",
        json={"name": "Jerry Drake"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Jerry Drake"


async def test_affiliate_cannot_update_user_other_field(
    affiliate_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await affiliate_client.put(
        f"/users/{user.id}",
        json={"email": "blueberries@breakfast.com"},
    )
    assert response.status_code == 422


async def test_operators_cannot_update_user_other_field(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await operations_client.put(
        f"/users/{user.id}",
        json={"email": "blueberries@breakfast.com"},
    )
    assert response.status_code == 422


async def test_operators_can_update_user_name(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await operations_client.put(
        f"/users/{user.id}",
        json={"name": "Daitarn3"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Daitarn3"


async def test_operators_cannot_update_user_with_empty_payload(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await operations_client.put(
        f"/users/{user.id}",
        json={},
    )
    assert response.status_code == 422


async def test_operators_cannot_update_user_with_name_None(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await operations_client.put(
        f"/users/{user.id}",
        json={"name": None},
    )
    assert response.status_code == 422


async def test_operators_cannot_update_a_deleted_user(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.DELETED,
    )

    response = await operations_client.put(
        f"/users/{user.id}",
        json={"name": "Batman"},
    )
    assert response.status_code == 400


async def test_affiliates_cannot_update_user_with_empty_payload(
    affiliate_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    response = await affiliate_client.put(
        f"/users/{user.id}",
        json={},
    )
    assert response.status_code == 422


#
# DELETE USER
#


async def test_affiliates_cannot_delete_user(
    affiliate_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    response = await affiliate_client.delete(f"/users/{user.id}")
    assert response.status_code == 403


async def test_operators_can_delete_user(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    response = await operations_client.delete(f"/users/{user.id}")
    assert response.status_code == 204


async def test_operators_try_to_delete_user_with_wrong_id(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    response = await operations_client.delete("/users/FUSR-4209-7117")
    assert response.status_code == 404


async def test_operator_cannot_delete_itself(
    operations_account: Account,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    jwt_token_factory: JWTTokenFactory,
    test_settings: Settings,
    accountuser_factory: ModelFactory[AccountUser],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.ACTIVE
    )
    jwt_token = jwt_token_factory(
        user.id, test_settings.auth_access_jwt_secret, account_id=operations_account.id
    )

    response = await api_client.delete(
        f"/users/{user.id}",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "A user cannot delete itself."


async def test_delete_with_multiple_accounts(
    operations_client: AsyncClient,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
    db_session: AsyncSession,
):
    accountusers = []
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )

    for _ in range(30):
        accountuser = await accountuser_factory(
            user_id=user.id, account_id=operations_account.id, status=AccountStatus.ACTIVE
        )
        accountusers.append(accountuser)
    response = await operations_client.delete(f"/users/{user.id}")
    assert response.status_code == 204
    await db_session.refresh(user)
    assert user.status == UserStatus.DELETED
    for accountuser in accountusers:
        await db_session.refresh(accountuser)
        assert accountuser.status == AccountUserStatus.DELETED


#


async def test_reset_password(
    test_settings: Settings,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
):
    user = await user_factory(
        pwd_reset_token="my-super-reset-token",
        pwd_reset_token_expires_at=datetime.now(UTC)
        + timedelta(minutes=test_settings.pwd_reset_token_length_expires_minutes),
    )

    response = await api_client.post(
        f"/users/{user.id}/reset-password",
        json={
            "pwd_reset_token": user.pwd_reset_token,
            "password": "MySuperSecurePassword01$",
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == user.id


@pytest.mark.parametrize(
    "user_status",
    [UserStatus.DELETED, UserStatus.DISABLED, UserStatus.DRAFT],
)
async def test_reset_password_invalid_status(
    test_settings: Settings,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    user_status: UserStatus,
):
    user = await user_factory(
        pwd_reset_token="my-super-reset-token",
        pwd_reset_token_expires_at=datetime.now(UTC)
        + timedelta(minutes=test_settings.pwd_reset_token_length_expires_minutes),
        status=user_status,
    )

    response = await api_client.post(
        f"/users/{user.id}/reset-password",
        json={
            "pwd_reset_token": user.pwd_reset_token,
            "password": "MySuperSecurePassword01$",
        },
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "You have summoned the mighty Error 400! It demands a better request."
    )


async def test_reset_password_no_token(
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
):
    user = await user_factory()

    response = await api_client.post(
        f"/users/{user.id}/reset-password",
        json={
            "pwd_reset_token": "my-fake-token",
            "password": "MySuperSecurePassword01$",
        },
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "You have summoned the mighty Error 400! It demands a better request."
    )


async def test_reset_password_token_expired(
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
):
    user = await user_factory(
        pwd_reset_token="my-super-reset-token",
        pwd_reset_token_expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )

    response = await api_client.post(
        f"/users/{user.id}/reset-password",
        json={
            "pwd_reset_token": user.pwd_reset_token,
            "password": "MySuperSecurePassword01$",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Your password reset token has expired."


async def test_reset_password_no_password(
    test_settings: Settings,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
):
    user = await user_factory(
        pwd_reset_token="my-super-reset-token",
        pwd_reset_token_expires_at=datetime.now(UTC)
        + timedelta(minutes=test_settings.pwd_reset_token_length_expires_minutes),
    )

    response = await api_client.post(
        f"/users/{user.id}/reset-password",
        json={
            "pwd_reset_token": user.pwd_reset_token,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Password is required."


@pytest.mark.parametrize(
    ("weak_passwd", "expected_msg"),
    [
        ("Sh0r!", "Must be at least 8 characters long"),
        ("l0ngbutw!thoutreqsym", "Must contain at least one uppercase letter (A-Z)"),
        ("L0NGBUTWITHOUTREQ$YM", "Must contain at least one lowercase letter (a-z)"),
        (
            "01234585858585",
            (
                "Must contain at least one uppercase letter (A-Z), Must contain at "
                "least one lowercase letter (a-z), Must contain at least one special "
                "character (e.g., !@#$%^&*)"
            ),
        ),
        (
            "@@@!!%$%!$!%!/((%))",
            (
                "Must contain at least one uppercase letter (A-Z), Must contain at "
                "least one lowercase letter (a-z), Must contain at least one number (0-9)"
            ),
        ),
    ],
)
async def test_reset_password_waek_password(
    test_settings: Settings,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    weak_passwd: str,
    expected_msg: str,
):
    user = await user_factory(
        pwd_reset_token="my-super-reset-token",
        pwd_reset_token_expires_at=datetime.now(UTC)
        + timedelta(minutes=test_settings.pwd_reset_token_length_expires_minutes),
    )

    response = await api_client.post(
        f"/users/{user.id}/reset-password",
        json={
            "pwd_reset_token": user.pwd_reset_token,
            "password": weak_passwd,
        },
    )
    assert response.status_code == 422
    [detail] = response.json()["detail"]
    assert detail["loc"] == ["body", "password"]
    assert detail["type"] == "value_error"
    assert detail["msg"] == f"Value error, {expected_msg}."
