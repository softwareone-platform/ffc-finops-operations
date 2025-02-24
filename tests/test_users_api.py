from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from httpx import AsyncClient
from pytest_mock import MockerFixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf import Settings
from app.db.models import Account, AccountUser, System, User
from app.enums import AccountStatus, AccountUserStatus, UserStatus
from app.hasher import pbkdf2_sha256
from tests.types import JWTTokenFactory, ModelFactory


@time_machine.travel("2025-03-07T10:00:00Z", tick=False)
async def test_invite_user(
    test_settings: Settings,
    mocker: MockerFixture,
    gcp_account: Account,
    gcp_extension: System,
    jwt_token_factory: JWTTokenFactory,
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    token = jwt_token_factory(gcp_extension.id, gcp_extension.jwt_secret)
    mocker.patch(
        "app.routers.users.secrets.token_urlsafe",
        return_value="invitation-token",
    )
    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Invited User"
    assert data["account_user"]["account"]["id"] == gcp_account.id
    assert data["account_user"]["invitation_token"] == "invitation-token"

    user = await db_session.get(User, data["id"])
    assert user is not None
    assert user.email == "invited@user.ops"
    assert user.status == UserStatus.DRAFT

    query = select(AccountUser).where(
        AccountUser.user_id == user.id,
        AccountUser.account_id == gcp_account.id,
        AccountUser.status == AccountUserStatus.INVITED,
    )

    result = await db_session.execute(query)
    account_user = result.scalars().first()
    assert account_user is not None
    assert account_user.invitation_token == "invitation-token"
    assert account_user.invitation_token_expires_at is not None
    assert account_user.invitation_token_expires_at == datetime.now(UTC) + timedelta(
        days=test_settings.invitation_token_expires_days,
    )


async def test_invite_user_to_second_account(
    gcp_account: Account,
    operations_account: Account,
    gcp_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.ACTIVE,
    )
    token = jwt_token_factory(gcp_extension.id, gcp_extension.jwt_secret)
    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Invited User"
    assert data["account_user"]["account"]["id"] == gcp_account.id

    assert data["id"] == user.id

    query = select(AccountUser).where(
        AccountUser.user_id == user.id,
        AccountUser.account_id == gcp_account.id,
        AccountUser.status == AccountUserStatus.INVITED,
    )

    result = await db_session.execute(query)
    account_user = result.scalars().first()
    assert account_user is not None


async def test_invite_by_operations_account(
    gcp_account: Account,
    operations_account: Account,
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.ACTIVE,
    )
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": gcp_account.id},
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Invited User"
    assert data["account_user"]["account"]["id"] == gcp_account.id

    assert data["id"] == user.id

    query = select(AccountUser).where(
        AccountUser.user_id == user.id,
        AccountUser.account_id == gcp_account.id,
        AccountUser.status == AccountUserStatus.INVITED,
    )

    result = await db_session.execute(query)
    account_user = result.scalars().first()
    assert account_user is not None


async def test_invite_by_operations_account_without_target_account(
    operations_account: Account,
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.ACTIVE,
    )
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == "Operations accounts must provide an account to invite a User."


async def test_invite_by_operations_account_target_account_not_found(
    operations_account: Account,
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.ACTIVE,
    )
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": "not-found"},
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == "No Active Account has been found with ID not-found."


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.DELETED, AccountStatus.DISABLED],
)
async def test_invite_by_operations_account_target_account_invalid_status(
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    account_factory: ModelFactory[Account],
    api_client: AsyncClient,
    account_status: AccountStatus,
):
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)
    account = await account_factory(status=account_status)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": account.id},
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == f"No Active Account has been found with ID {account.id}."


async def test_invite_user_by_affiliate_to_other_account(
    mocker: MockerFixture,
    aws_account: Account,
    gcp_extension: System,
    jwt_token_factory: JWTTokenFactory,
    api_client: AsyncClient,
):
    token = jwt_token_factory(gcp_extension.id, gcp_extension.jwt_secret)
    mocker.patch(
        "app.routers.users.secrets.token_urlsafe",
        return_value="invitation-token",
    )
    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": aws_account.id},
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == "Affiliate accounts can only invite users to the same Account."


async def test_invite_by_operations_account_user_disabled(
    operations_account: Account,
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
):
    await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.DISABLED,
    )
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": operations_account.id},
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == ("The user invited@user.ops cannot be invited " "because it is disabled.")


@pytest.mark.parametrize(
    "accountuser_status",
    [AccountUserStatus.INVITED, AccountUserStatus.INVITATION_EXPIRED],
)
async def test_invite_by_operations_account_already_invited(
    affiliate_account: Account,
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    accountuser_status: AccountUserStatus,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=affiliate_account.id,
        status=accountuser_status,
    )
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": affiliate_account.id},
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == (
        "The user invited@user.ops has already been "
        f"invited to the account: {affiliate_account.id}."
    )


async def test_invite_by_operations_already_belong_to_account(
    affiliate_account: Account,
    ffc_extension: System,
    jwt_token_factory: JWTTokenFactory,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Invited User",
        email="invited@user.ops",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=affiliate_account.id,
        status=AccountUserStatus.ACTIVE,
    )
    token = jwt_token_factory(ffc_extension.id, ffc_extension.jwt_secret)

    response = await api_client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user": {
                "name": "Invited User",
                "email": "invited@user.ops",
            },
            "account": {"id": affiliate_account.id},
        },
    )
    assert response.status_code == 400
    error = response.json()["detail"]
    assert error == (
        "The user invited@user.ops already " f"belong to the account: {affiliate_account.id}."
    )


@time_machine.travel("2025-03-07T10:00:00", tick=False)
async def test_accept_invitation(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Test Invited User",
        status=UserStatus.DRAFT,
    )
    account_user = await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 200
    await db_session.refresh(account_user)
    assert account_user.status == AccountUserStatus.ACTIVE
    assert account_user.joined_at is not None
    assert account_user.joined_at == datetime.now(UTC)
    assert account_user.invitation_token is None
    assert account_user.invitation_token_expires_at is None

    await db_session.refresh(user)
    assert user.status == UserStatus.ACTIVE
    assert user.password is not None
    assert pbkdf2_sha256.verify("Passw0rd!", user.password) is True


async def test_accept_invitation_user_not_found(api_client: AsyncClient):
    response = await api_client.post(
        "/users/FUSR-1234-5678/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 404


@pytest.mark.parametrize("user_status", [UserStatus.DELETED, UserStatus.DISABLED])
async def test_accept_invitation_user_not_found_invalid_status(
    user_factory: ModelFactory[User],
    api_client: AsyncClient,
    user_status: UserStatus,
):
    user = await user_factory(status=user_status)
    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 404


async def test_accept_invitation_accountuser_deleted(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    api_client: AsyncClient,
):
    user = await user_factory(status=UserStatus.DRAFT)
    await accountuser_factory(
        user_id=user.id, account_id=operations_account.id, status=AccountUserStatus.DELETED
    )
    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invitation not found."


async def test_accept_invitation_invalid_token(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    api_client: AsyncClient,
):
    user = await user_factory(status=UserStatus.DRAFT)
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.INVITED,
        invitation_token="test-invitation-token",
    )
    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "different-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invitation not found."


@pytest.mark.parametrize(
    "accountuser_status", [AccountUserStatus.INVITED, AccountUserStatus.INVITATION_EXPIRED]
)
async def test_accept_invitation_expired(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    db_session: AsyncSession,
    api_client: AsyncClient,
    accountuser_status: AccountUserStatus,
):
    user = await user_factory(status=UserStatus.DRAFT)
    account_user = await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=accountuser_status,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invitation has expired."
    await db_session.refresh(account_user)
    assert account_user.status == AccountUserStatus.INVITATION_EXPIRED


@pytest.mark.parametrize("account_status", [AccountStatus.DELETED, AccountStatus.DISABLED])
async def test_accept_invitation_inactive_account(
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
    accountuser_factory: ModelFactory[AccountUser],
    api_client: AsyncClient,
    account_status: AccountStatus,
):
    user = await user_factory(status=UserStatus.DRAFT)
    account = await account_factory(status=account_status)
    await accountuser_factory(
        user_id=user.id,
        account_id=account.id,
        status=AccountUserStatus.INVITED,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "The Account related to this invitation is not Active."


async def test_accept_invitation_draft_user_no_password(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Test Invited User",
        status=UserStatus.DRAFT,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Password is required for Draft users."


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
async def test_accept_invitation_draft_user_weak_password(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    api_client: AsyncClient,
    weak_passwd: str,
    expected_msg: str,
):
    user = await user_factory(
        name="Test Invited User",
        status=UserStatus.DRAFT,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": weak_passwd,
        },
    )
    assert response.status_code == 422
    [detail] = response.json()["detail"]
    assert detail["loc"] == ["body", "password"]
    assert detail["type"] == "value_error"
    assert detail["msg"] == f"Value error, {expected_msg}."


async def test_accept_invitation_active_user_with_password(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Test Invited User",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={
            "invitation_token": "test-invitation-token",
            "password": "Passw0rd!",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "A password cannot be provided for an Active User."


@time_machine.travel("2025-03-07T10:00:00", tick=False)
async def test_accept_invitation_second_account(
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    operations_account: Account,
    affiliate_account: Account,
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    user = await user_factory(
        name="Test Invited User",
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.ACTIVE,
    )
    account_user = await accountuser_factory(
        user_id=user.id,
        account_id=affiliate_account.id,
        invitation_token="test-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await api_client.post(
        f"/users/{user.id}/accept-invitation",
        json={"invitation_token": "test-invitation-token"},
    )
    assert response.status_code == 200
    await db_session.refresh(account_user)
    assert account_user.status == AccountUserStatus.ACTIVE


@time_machine.travel("2025-03-07T10:00:00Z", tick=False)
@pytest.mark.parametrize(
    "accountuser_status",
    [AccountUserStatus.INVITED, AccountUserStatus.INVITATION_EXPIRED],
)
async def test_resend_invitation(
    test_settings: Settings,
    mocker: MockerFixture,
    gcp_account: Account,
    gcp_extension: System,
    jwt_token_factory: JWTTokenFactory,
    api_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    accountuser_status: AccountUserStatus,
):
    user = await user_factory(
        status=UserStatus.ACTIVE,
    )
    await accountuser_factory(
        user_id=user.id,
        account_id=gcp_account.id,
        invitation_token="current-invitation-token",
        invitation_token_expires_at=datetime.now(UTC) - timedelta(days=1),
        status=accountuser_status,
    )
    token = jwt_token_factory(gcp_extension.id, gcp_extension.jwt_secret)
    mocker.patch(
        "app.routers.users.secrets.token_urlsafe",
        return_value="new-invitation-token",
    )
    response = await api_client.post(
        f"/users/{user.id}/accounts/{gcp_account.id}/resend-invitation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["account_user"]["invitation_token"] == "new-invitation-token"

    query = select(AccountUser).where(
        AccountUser.user_id == user.id,
        AccountUser.account_id == gcp_account.id,
        AccountUser.status == AccountUserStatus.INVITED,
    )

    result = await db_session.execute(query)
    account_user = result.scalars().first()
    assert account_user is not None
    assert account_user.invitation_token == "new-invitation-token"
    assert account_user.invitation_token_expires_at is not None
    assert account_user.invitation_token_expires_at == datetime.now(UTC) + timedelta(
        days=test_settings.invitation_token_expires_days,
    )


async def test_resend_invitation_user_not_found(
    gcp_jwt_token: str,
    api_client: AsyncClient,
):
    response = await api_client.post(
        "/users/FUSR-1234-5678/accounts/FACC-1234-5678/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 404


async def test_resend_invitation_user_deleted(
    gcp_jwt_token: str,
    api_client: AsyncClient,
    user_factory: ModelFactory[User],
):
    user = await user_factory(
        status=UserStatus.DELETED,
    )
    response = await api_client.post(
        f"/users/{user.id}/accounts/FACC-1234-5678/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 404


async def test_resend_invitation_account_not_found(
    gcp_jwt_token: str,
    api_client: AsyncClient,
    user_factory: ModelFactory[User],
):
    user = await user_factory()
    response = await api_client.post(
        f"/users/{user.id}/accounts/FACC-1234-5678/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 404


async def test_resend_invitation_different_account(
    gcp_jwt_token: str,
    api_client: AsyncClient,
    user_factory: ModelFactory[User],
    account_factory: ModelFactory[Account],
):
    user = await user_factory()
    account = await account_factory()
    response = await api_client.post(
        f"/users/{user.id}/accounts/{account.id}/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 404


async def test_resend_invitation_no_account_user(
    gcp_jwt_token: str,
    api_client: AsyncClient,
    gcp_account: Account,
    user_factory: ModelFactory[User],
):
    user = await user_factory()
    response = await api_client.post(
        f"/users/{user.id}/accounts/{gcp_account.id}/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert (
        f"No invitation to Account with ID `{gcp_account.id}` "
        f"was found for User with ID `{user.id}."
    ) == detail


async def test_resend_invitation_account_user_deleted(
    gcp_jwt_token: str,
    api_client: AsyncClient,
    gcp_account: Account,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
):
    user = await user_factory()
    await accountuser_factory(
        user_id=user.id, account_id=gcp_account.id, status=AccountUserStatus.DELETED
    )
    response = await api_client.post(
        f"/users/{user.id}/accounts/{gcp_account.id}/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert (
        f"No invitation to Account with ID `{gcp_account.id}` "
        f"was found for User with ID `{user.id}."
    ) == detail


async def test_resend_invitation_account_user_active(
    gcp_jwt_token: str,
    api_client: AsyncClient,
    gcp_account: Account,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
):
    user = await user_factory()
    await accountuser_factory(
        user_id=user.id, account_id=gcp_account.id, status=AccountUserStatus.ACTIVE
    )
    response = await api_client.post(
        f"/users/{user.id}/accounts/{gcp_account.id}/resend-invitation",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert (f"User with ID `{user.id}` already belong to the Account with ID `{user.id}.") == detail


# -----------
# GET USER BY ID
# -----------


class TestGetUserById:
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
        self,
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
            invitation_token_expires_at=datetime.now()
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
        self,
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
            invitation_token_expires_at=datetime.now()
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

    async def test_cannot_get_user_by_id_with_affiliate_account_client_and_not_existing_user(  # noqa: E501
        self, affiliate_client: AsyncClient
    ):
        response = await affiliate_client.get("/users/FUSR-8994-8942")
        assert response.status_code == 404
