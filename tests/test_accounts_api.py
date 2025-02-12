from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, System
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
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Microsoft"
    assert data["external_id"] == "ACC-9044-8753"
    assert data["type"] == "affiliate"


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
    print("--- DATA-- :\n", data)
    """
     {'name': 'Microsoft', 
     'external_id': 'cc2f4d07-f80a-45bc-9b3e-3473e23cec63', 
     'type': 'affiliate', 
     'created_at': '2025-02-12T10:53:14.752084Z', 
     'updated_at': '2025-02-12T10:53:14.752087Z', 
     'deleted_at': None, 'created_by': {'id': 'FTKN-3532-2325', 'type': 'system', 'name': 'James-Wolfe'},
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
    operations_account,
    api_client: AsyncClient,
    ffc_jwt_token: str
):
    response = await api_client.get(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == data["total"]
