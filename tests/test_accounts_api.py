from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, System


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
