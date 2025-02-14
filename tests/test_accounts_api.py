from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from httpx import AsyncClient
from pytest_mock import MockerFixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, System
from app.dependencies import AccountRepository
from app.enums import AccountStatus, AccountType
from app.routers.accounts import (
    validate_account_type_and_required_conditions,
    validate_required_conditions_before_update,
)
from app.schemas import AccountCreate
from tests.types import JWTTokenFactory, ModelFactory

# ====================
# Authentication Tests
# ====================


async def test_get_entitlements_without_token(api_client: AsyncClient):
    response = await api_client.get("/accounts")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_get_entitlements_with_invalid_token(api_client: AsyncClient):
    response = await api_client.get(
        "/accounts",
        headers={"Authorization": "Bearer invalid.token.here"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_get_entitlements_with_expired_token(
    api_client: AsyncClient,
    jwt_token_factory: JWTTokenFactory,
    gcp_extension: System,
):
    expired_time = datetime.now(UTC) - timedelta(hours=1)
    expired_token = jwt_token_factory(
        str(gcp_extension.id),
        gcp_extension.jwt_secret,
        exp=expired_time,
    )

    response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


# ====================
# Create Accounts Tests
# ====================


async def test_can_create_accounts(
    api_client: AsyncClient,
    ffc_jwt_token: str,
    ffc_extension: System,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"name": "Microsoft", "external_id": "ACC-9044-8753", "type": "affiliate"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Microsoft"
    assert data["external_id"] == "ACC-9044-8753"
    assert data["type"] == "affiliate"
    assert data["status"] == "active"
    assert data["created_at"] is not None
    assert data["created_by"]["id"] == str(ffc_extension.id)
    assert data["created_by"]["type"] == ffc_extension.type
    assert data["created_by"]["name"] == ffc_extension.name
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(ffc_extension.id)
    assert data["updated_by"]["type"] == ffc_extension.type
    assert data["updated_by"]["name"] == ffc_extension.name

    result = await db_session.execute(select(Account).where(Account.id == data["id"]))
    assert result.one_or_none() is not None


async def test_create_accounts_type_not_affiliate(
    api_client: AsyncClient,
    ffc_jwt_token: str,
    ffc_extension: System,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"name": "Microsoft", "external_id": "ACC-9044-8753", "type": "operations"},
    )
    assert response.status_code == 400

    response = await api_client.post(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"external_id": "ACC-9044-8753", "type": "affiliate"},
    )
    assert response.status_code == 422

    response = await api_client.post(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"name": "Microsoft", "type": "affiliate"},
    )
    assert response.status_code == 422


async def test_create_accounts_incomplete_body(
    api_client: AsyncClient,
    ffc_jwt_token: str,
    ffc_extension: System,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"name": "Microsoft", "external_id": "ACC-9044-8753"},
    )
    assert response.status_code == 422


async def test_cannot_create_accounts_if_context_is_not_operations_account(
    affiliate_account: Account, affiliate_client: AsyncClient
):
    response = await affiliate_client.post(
        "/accounts",
        json={"name": "Microsoft", "external_id": "ACC-9044-8753", "type": "affiliate"},
    )
    data = response.json()
    assert response.status_code == 403
    assert data.get("detail") == "You've found the door, but you don't have the key."


# ====================
# Get Accounts Tests
# ====================


async def test_get_account_by_id(
    affiliate_account: Account,
    api_client: AsyncClient,
    ffc_jwt_token: str,
    ffc_extension: System,
):
    response = await api_client.get(
        f"/accounts/{affiliate_account.id}",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    """
     {'name': 'Microsoft',
     'external_id': 'cc2f4d07-f80a-45bc-9b3e-3473e23cec63',
     'type': 'affiliate',
     'created_at': '2025-02-12T10:53:14.752084Z',
     'updated_at': '2025-02-12T10:53:14.752087Z',
     'deleted_at': None, 'created_by': {'id': 'FTKN-3532-2325', 'type': 'system',
     'name': 'James-Wolfe'},
      'updated_by': {'id': 'FTKN-3532-2325', 'type': 'system', 'name': 'James-Wolfe'},
      'deleted_by': None,
      'id': 'FACC-8751-0928',
      'entitlements_stats': None, 'status': 'active'
      }
    """
    assert data["id"] == affiliate_account.id
    assert data["name"] == affiliate_account.name
    assert data["external_id"] == affiliate_account.external_id
    assert data["type"] == affiliate_account.type
    assert data["status"] == affiliate_account.status
    assert data["created_at"] is not None
    assert data["created_by"]["id"] == str(ffc_extension.id)
    assert data["created_by"]["type"] == ffc_extension.type
    assert data["created_by"]["name"] == ffc_extension.name
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(ffc_extension.id)
    assert data["updated_by"]["type"] == ffc_extension.type
    assert data["updated_by"]["name"] == ffc_extension.name


async def test_get_invalid_account(api_client: AsyncClient, ffc_jwt_token: str):
    id = "FACC-1369-9180"
    response = await api_client.get(
        f"/accounts/{id}",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Account with ID `{id}` wasn't found"


async def test_get_invalid_id_format(api_client: AsyncClient, ffc_jwt_token: str):
    response = await api_client.get(
        "/accounts/this-is-not-a-valid-uuid",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 422

    [detail] = response.json()["detail"]
    assert detail["loc"] == ["path", "id"]
    assert detail["type"] == "string_pattern_mismatch"


async def test_get_all_accounts(api_client: AsyncClient, ffc_jwt_token: str):
    response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_get_all_accounts_single_page(
    operations_account, api_client: AsyncClient, ffc_jwt_token: str
):
    response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == data["total"]


async def test_get_all_account_multiple_pages(
    account_factory: ModelFactory[Account],
    api_client: AsyncClient,
    gcp_extension: System,
    gcp_account: Account,
    ffc_jwt_token: str,
):
    for _ in range(10):
        await account_factory(
            name="SWO",
            type=AccountType.OPERATIONS,
            status=AccountStatus.ACTIVE,
            external_id=str(uuid4()),
        )

    first_page_response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        params={"limit": 5},
    )
    first_page_data = first_page_response.json()
    assert first_page_response.status_code == 200
    assert first_page_data["total"] == 12
    assert len(first_page_data["items"]) == 5
    assert first_page_data["limit"] == 5
    assert first_page_data["offset"] == 0

    second_page_response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        params={"limit": 3, "offset": 5},
    )
    second_page_data = second_page_response.json()

    assert second_page_response.status_code == 200
    assert second_page_data["total"] == 12
    assert len(second_page_data["items"]) == 3
    assert second_page_data["limit"] == 3
    assert second_page_data["offset"] == 5

    third_page_response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        params={"offset": 8},
    )
    third_page_data = third_page_response.json()

    assert third_page_response.status_code == 200
    assert third_page_data["total"] == 12
    assert len(third_page_data["items"]) == 4
    assert third_page_data["limit"] > 2
    assert third_page_data["offset"] == 8

    all_items = first_page_data["items"] + second_page_data["items"] + third_page_data["items"]
    assert len(all_items) == 12


# ====================
# Validation Functions Tests
# ====================


async def test_validate_account_type_and_required_conditions_account_type_operations():
    account_repo = AccountRepository

    data = AccountCreate(name="Microsoft", external_id=str(uuid4()), type=AccountType.OPERATIONS)
    with pytest.raises(HTTPException) as exc_info:
        await validate_account_type_and_required_conditions(account_repo, data)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "You cannot create an Account of type Operations."


async def test_validate_account_type_and_required_conditions_account_deleted(
    mocker: MockerFixture,
):
    account_repo = mocker.Mock()
    account_repo.first = AsyncMock(return_value=True)

    data = AccountCreate(name="Microsoft", external_id="ACC-9044-8753", type=AccountType.AFFILIATE)

    with pytest.raises(HTTPException) as exc_info:
        await validate_account_type_and_required_conditions(account_repo, data)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "An Account with external ID `ACC-9044-8753` already exists." in str(
        exc_info.value.detail
    )


async def test_validate_required_conditions_before_update_account_type_operations(
    operations_account: Account,
):
    with pytest.raises(HTTPException) as exc_info:
        await validate_required_conditions_before_update(account=operations_account)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "You cannot update an Account of type Operations."


async def test_validate_required_conditions_before_update_account_deleted():
    account = Account(name="Microsoft", external_id="ACC-9044-8753", type=AccountType.AFFILIATE)
    account.status = AccountStatus.DELETED
    with pytest.raises(HTTPException) as exc_info:
        await validate_required_conditions_before_update(account=account)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "You cannot update an Account Deleted." in str(exc_info.value.detail)


# =================
# UPDATE Accounts
# =================


async def test_can_update_accounts_name(
    operations_client: AsyncClient,
    ffc_extension: System,
    affiliate_account: Account,
    db_session: AsyncSession,
):
    response = await operations_client.put(
        f"/accounts/{affiliate_account.id}",
        json={"name": "AWS"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "AWS"
    assert data["external_id"] == affiliate_account.external_id
    assert data["type"] == affiliate_account.type
    assert data["status"] == affiliate_account.status
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(ffc_extension.id)
    assert data["updated_by"]["type"] == ffc_extension.type
    assert data["updated_by"]["name"] == ffc_extension.name

    result = await db_session.execute(select(Account).where(Account.id == data["id"]))
    assert result.one_or_none() is not None


async def test_can_update_accounts_external_id(
    operations_client: AsyncClient,
    ffc_extension: System,
    affiliate_account: Account,
    db_session: AsyncSession,
):
    response = await operations_client.put(
        f"/accounts/{affiliate_account.id}",
        json={"external_id": "ACC-9044-8753"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Microsoft"
    assert data["external_id"] == "ACC-9044-8753"
    assert data["type"] == affiliate_account.type
    assert data["status"] == affiliate_account.status
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(ffc_extension.id)
    assert data["updated_by"]["type"] == ffc_extension.type
    assert data["updated_by"]["name"] == ffc_extension.name

    result = await db_session.execute(select(Account).where(Account.id == data["id"]))
    assert result.one_or_none() is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("account_status", [AccountStatus.DELETED, AccountStatus.DISABLED])
async def test_cannot_update_if_status_is_not_active(
    api_client: AsyncClient,
    ffc_jwt_token: str,
    account_factory: ModelFactory[Account],
    account_status: AccountStatus,
):
    account = await account_factory(
        status=account_status,
        type=AccountType.AFFILIATE,
        name="Microsoft",
        external_id="ACC-9044-8753",
    )
    response = await api_client.put(
        f"/accounts/{account.id}",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"name": "AWS"},
    )
    assert response.status_code == 400


async def test_cannot_update_disabled_accounts(
    operations_client: AsyncClient,
    affiliate_account: Account,
):
    response = await operations_client.put(
        f"/accounts/{affiliate_account.id}",
        json={"status": AccountStatus.DISABLED},
    )
    data = response.json()
    assert response.status_code == 400
    assert data.get("detail") == "You can't update whatever you want."


async def test_cannot_update_accounts_if_context_is_not_operations_account(
    affiliate_account: Account, affiliate_client: AsyncClient
):
    response = await affiliate_client.put(
        f"/accounts/{affiliate_account.id}",
        json={"name": "AWS"},
    )
    data = response.json()
    assert response.status_code == 403
    assert data.get("detail") == "You've found the door, but you don't have the key."


async def test_can_only_updated_the_name_and_external_id(
    operations_client: AsyncClient,
    affiliate_account: Account,
):
    response = await operations_client.put(
        f"/accounts/{affiliate_account.id}",
        json={"type": AccountType.OPERATIONS},
    )
    data = response.json()
    assert response.status_code == 400
    assert data.get("detail") == "You can't update whatever you want."

    response = await operations_client.put(
        f"/accounts/{affiliate_account.id}",
        json={"status": AccountStatus.DISABLED},
    )
    data = response.json()
    assert response.status_code == 400
    assert data.get("detail") == "You can't update whatever you want."
