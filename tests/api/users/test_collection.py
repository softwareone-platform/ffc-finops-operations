from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf import Settings
from app.db.handlers import AccountUserHandler, NotFoundError
from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountType, AccountUserStatus, UserStatus
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
    ("useraccount_status", "http_status"),
    [
        (AccountUserStatus.ACTIVE, 200),
        (AccountUserStatus.INVITED, 200),
        (AccountUserStatus.INVITATION_EXPIRED, 200),
        (AccountUserStatus.DELETED, 200),
    ],
)
async def test_operators_can_always_list_users_with_email_in_filter(
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

    response = await operations_client.get("/users?eq(email,peter.parker@spiderman.com)")
    data = response.json()
    assert response.status_code == http_status
    assert data.get("items")[0]["email"] == "peter.parker@spiderman.com"
    assert isinstance(data.get("items"), list)


async def test_get_user_with_status_in_filter(
    operations_client: AsyncClient,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.ACTIVE
    )

    response = await operations_client.get("/users?eq(status,active)")
    data = response.json()
    assert response.status_code == 200
    assert data.get("items")[0]["email"] == "peter.parker@spiderman.com"
    assert isinstance(data.get("items"), list)


async def test_get_user_with_created_at_in_filter(
    operations_client: AsyncClient,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.ACTIVE
    )

    response = await operations_client.get(
        f"/users?eq(events.created.at,{user.created_at.isoformat()})"
    )
    data = response.json()
    assert response.status_code == 200
    assert data.get("items")[0]["email"] == "peter.parker@spiderman.com"
    assert isinstance(data.get("items"), list)


async def test_get_user_with_updated_at_in_filter(
    operations_client: AsyncClient,
    operations_account: Account,
    accountuser_factory: ModelFactory[AccountUser],
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.ACTIVE
    )

    response = await operations_client.get(
        f"/users?eq(events.updated.at,{user.updated_at.isoformat()})"
    )
    data = response.json()
    assert response.status_code == 200
    assert data.get("items")[0]["email"] == "peter.parker@spiderman.com"
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
    user_factory: ModelFactory[User],
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
# Enable User
##


async def test_operator_can_enable_disabled_user(
    operations_client: AsyncClient,
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.DISABLED,
    )

    response = await operations_client.post(f"/users/{user.id}/enable")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == UserStatus.ACTIVE


@pytest.mark.parametrize(
    "user_status",
    [
        UserStatus.DELETED,
        UserStatus.ACTIVE,
        UserStatus.DRAFT,
    ],
)
async def test_operator_cannot_enable_not_active_user(
    operations_client: AsyncClient, user_factory: ModelFactory[User], user_status: str
):
    user = await user_factory(
        name="Peter Parker", email="peter.parker@spiderman.com", status=user_status
    )
    response = await operations_client.post(f"/users/{user.id}/enable")
    assert response.status_code == 400
    data = response.json()
    status = user_status.split(".")[0]
    assert data["detail"] == f"User's status is '{status}' only disabled users can be enabled."


async def test_operator_cannot_enable_itself(
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
        f"/users/{user.id}/enable",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "A user cannot enable itself."


@pytest.mark.parametrize(
    "user_status",
    [
        UserStatus.DELETED,
        UserStatus.ACTIVE,
        UserStatus.DISABLED,
        UserStatus.DRAFT,
    ],
)
async def test_affiliate_cannot_enable_user(
    affiliate_client: AsyncClient,
    user_factory: ModelFactory[User],
    user_status: str,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=user_status,
    )
    response = await affiliate_client.post(f"/users/{user.id}/enable")
    assert response.status_code == 403
    data = response.json()
    assert data["detail"] == "You've found the door, but you don't have the key."


##
# Update User
##


async def test_affiliate_can_update_user_name(
    affiliate_client: AsyncClient,
    user_factory: ModelFactory[User],
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


async def test_user_can_update_its_name(
    test_settings: Settings,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    affiliate_account: Account,
    jwt_token_factory: JWTTokenFactory,
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(user_id=user.id, account_id=affiliate_account.id)

    token = jwt_token_factory(
        user.id,
        test_settings.auth_access_jwt_secret,
        account_id=affiliate_account.id,
    )

    response = await api_client.put(
        f"/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
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


##
# Delete User
##


async def test_try_to_delete_with_a_deleted_user(
    operations_client: AsyncClient, user_factory: ModelFactory[User]
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.DELETED,
    )
    response = await operations_client.delete(f"/users/{user.id}")
    data = response.json()
    assert response.status_code == 400
    assert data["detail"] == "The user has already been deleted."


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
##
# Reset Password
##


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


# ---------------------
# GET ACCOUNTS FOR USER
# ---------------------


@dataclass
class GetAccountsForUserTestCase:
    caller_account_type: AccountType
    user_status: UserStatus = UserStatus.ACTIVE
    account_user_status: AccountUserStatus = AccountUserStatus.ACTIVE
    account_status: AccountStatus = AccountStatus.ACTIVE
    account_type: AccountType = AccountType.AFFILIATE
    expected_status_code: int = status.HTTP_200_OK
    expected_items: int = 1


TEST_CASES = {
    "all_active_affiliate": GetAccountsForUserTestCase(caller_account_type=AccountType.AFFILIATE),
    "deleted_user_affiliate": GetAccountsForUserTestCase(
        caller_account_type=AccountType.AFFILIATE,
        user_status=UserStatus.DELETED,
        expected_status_code=status.HTTP_404_NOT_FOUND,
    ),
    "deleted_account_user_affiliate": GetAccountsForUserTestCase(
        caller_account_type=AccountType.AFFILIATE,
        account_user_status=AccountUserStatus.DELETED,
        expected_items=0,
    ),
    "all_active_operations": GetAccountsForUserTestCase(caller_account_type=AccountType.OPERATIONS),
    "deleted_user_operations": GetAccountsForUserTestCase(
        caller_account_type=AccountType.OPERATIONS,
        user_status=UserStatus.DELETED,
        expected_status_code=status.HTTP_200_OK,
        expected_items=1,
    ),
    "deleted_account_user_operations": GetAccountsForUserTestCase(
        caller_account_type=AccountType.OPERATIONS,
        account_user_status=AccountUserStatus.DELETED,
        expected_items=1,
    ),
    "deleted_account_operations": GetAccountsForUserTestCase(
        caller_account_type=AccountType.OPERATIONS,
        account_status=AccountStatus.DELETED,
        expected_items=1,
    ),
}


@pytest.mark.parametrize(
    "test_case", [pytest.param(test_case, id=id) for id, test_case in TEST_CASES.items()]
)
async def test_list_user_accounts_single_account(
    api_client: AsyncClient,
    db_session: AsyncSession,
    account_factory: ModelFactory[Account],
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    ffc_jwt_token: str,
    gcp_jwt_token: str,
    test_case: GetAccountsForUserTestCase,
):
    account = await account_factory(
        name="Test Account",
        type=AccountType.AFFILIATE,
        status=test_case.account_status,
        external_id="test_account_external_id",
    )
    user = await user_factory(
        name="Test User",
        email="test.user@example.com",
        status=test_case.user_status,
        account=account,
        accountuser_status=test_case.account_user_status,
    )
    account_user = await AccountUserHandler(db_session).get_account_user(
        user_id=user.id, account_id=account.id
    )

    assert account_user is not None

    if test_case.caller_account_type == AccountType.OPERATIONS:
        api_client.headers["Authorization"] = f"Bearer {ffc_jwt_token}"
    elif test_case.caller_account_type == AccountType.AFFILIATE:
        api_client.headers["Authorization"] = f"Bearer {gcp_jwt_token}"
    else:
        raise RuntimeError("Invalid branch")

    response = await api_client.get(f"/users/{user.id}/accounts")
    assert response.status_code == test_case.expected_status_code
    data = response.json()

    if response.status_code == 404:
        assert data["detail"] == f"User with ID `{user.id}` wasn't found."
        return

    assert data["total"] == test_case.expected_items
    assert len(data["items"]) == test_case.expected_items

    if test_case.expected_items == 0:
        return

    response_account = data["items"][0]

    assert response_account["id"] == account.id
    assert response_account["status"] == account.status
    assert response_account["external_id"] == account.external_id
    assert response_account["type"] == account.type
    assert response_account["account_user"]["id"] == account_user.id
    assert response_account["account_user"]["status"] == account_user.status
    assert response_account["account_user"]["user"]["id"] == user.id
    assert response_account["account_user"]["user"]["email"] == user.email
    assert response_account["account_user"]["user"]["name"] == user.name

    assert datetime.fromisoformat(response_account["events"]["created"]["at"]) == account.created_at
    assert datetime.fromisoformat(response_account["events"]["updated"]["at"]) == account.updated_at
    assert response_account["events"].get("deleted") is None


@pytest.mark.parametrize(
    ("create_accounts_count", "limit", "offset", "expected_total", "expected_items_count"),
    [
        (100, None, None, 100, 50),
        (100, 10, None, 100, 10),
        (100, None, 95, 100, 5),
        (100, 10, 95, 100, 5),
        (2, 5, 1, 2, 1),
    ],
)
async def test_list_user_accounts_multiple_accounts(
    operations_client: AsyncClient,
    db_session: AsyncSession,
    create_accounts_count: int,
    limit: int | None,
    offset: int | None,
    expected_total: int,
    expected_items_count: int,
):
    user = User(name="Test User", email="test.user@example.com", status=UserStatus.ACTIVE)
    db_session.add(user)

    for i in range(create_accounts_count):
        account = Account(
            name=f"Test Account {i}",
            type=AccountType.AFFILIATE,
            status=AccountStatus.ACTIVE,
            external_id=f"test-account-external-id-{i}",
        )
        account_user = AccountUser(
            account=account,
            user=user,
            status=AccountUserStatus.ACTIVE,
        )
        db_session.add(account_user)
        db_session.add(account)

    await db_session.commit()

    params = {}

    if limit is not None:
        params["limit"] = limit

    if offset is not None:
        params["offset"] = offset

    response = await operations_client.get(f"/users/{user.id}/accounts", params=params)

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == expected_total
    assert len(data["items"]) == expected_items_count


async def test_list_user_accounts_multiple_users(
    operations_client: AsyncClient,
    db_session: AsyncSession,
):
    first_account = Account(name="First Account", external_id="test_account_1_external_id")
    second_account = Account(name="Second Account", external_id="test_account_2_external_id")

    first_user = User(name="First User", email="first.user@example.com")
    second_user = User(name="Second User", email="second.user@example.com")
    third_user = User(name="Third User", email="third.user@example.com")

    db_session.add_all([first_account, second_account, first_user, second_user, third_user])
    await db_session.commit()

    first_user_in_first_account = AccountUser(user_id=first_user.id, account_id=first_account.id)
    first_user_in_second_account = AccountUser(user_id=first_user.id, account_id=second_account.id)
    second_user_in_second_account = AccountUser(
        user_id=second_user.id, account_id=second_account.id
    )

    db_session.add_all(
        [
            first_user_in_first_account,
            first_user_in_second_account,
            second_user_in_second_account,
        ]
    )
    await db_session.commit()

    first_user_accounts_response = await operations_client.get(f"/users/{first_user.id}/accounts")
    assert first_user_accounts_response.status_code == status.HTTP_200_OK
    first_user_accounts_data = first_user_accounts_response.json()

    assert first_user_accounts_data["total"] == 2
    assert len(first_user_accounts_data["items"]) == 2

    response_account_ids = {account["id"] for account in first_user_accounts_data["items"]}
    response_useraccount_ids = {
        account["account_user"]["id"] for account in first_user_accounts_data["items"]
    }
    response_user_ids = {
        account["account_user"]["user"]["id"] for account in first_user_accounts_data["items"]
    }

    assert response_account_ids == {first_account.id, second_account.id}
    assert response_useraccount_ids == {
        first_user_in_first_account.id,
        first_user_in_second_account.id,
    }
    assert response_user_ids == {first_user.id}

    second_user_accounts_response = await operations_client.get(f"/users/{second_user.id}/accounts")
    assert second_user_accounts_response.status_code == status.HTTP_200_OK
    second_user_accounts_data = second_user_accounts_response.json()

    assert second_user_accounts_data["total"] == 1
    assert len(second_user_accounts_data["items"]) == 1

    response_account = second_user_accounts_data["items"][0]
    assert response_account["id"] == second_account.id
    assert response_account["account_user"]["id"] == second_user_in_second_account.id
    assert response_account["account_user"]["user"]["id"] == second_user.id

    third_user_accounts_response = await operations_client.get(f"/users/{third_user.id}/accounts")
    assert third_user_accounts_response.status_code == status.HTTP_200_OK
    third_user_accounts_data = third_user_accounts_response.json()

    assert third_user_accounts_data["total"] == 0
    assert third_user_accounts_data["items"] == []
