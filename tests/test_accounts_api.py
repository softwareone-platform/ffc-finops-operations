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
    print("DATA:", data)
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
    assert response.status_code == 400

    response = await api_client.post(
        "/accounts",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={"name": "Microsoft", "type": "affiliate"},
    )
    assert response.status_code == 400


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

# async def test_get_paginated_accounts_list(
#     account_factory: ModelFactory[Account],
#     api_client: AsyncClient,
#     ffc_jwt_token: str,
#     ffc_extension: System,
#     db_session: AsyncSession,
# ):
#
#
#
