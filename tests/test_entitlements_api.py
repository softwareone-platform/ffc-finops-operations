import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entitlement, System
from app.schemas import EntitlementRead, from_orm
from tests.conftest import ModelFactory
from tests.utils import assert_json_contains_model

# ====================
# Authentication Tests
# ====================


async def test_get_entitlements_without_token(api_client: AsyncClient):
    response = await api_client.get("/entitlements/")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_get_entitlements_with_invalid_token(api_client: AsyncClient):
    response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": "Bearer invalid.token.here"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_get_entitlements_with_expired_token(
    api_client: AsyncClient,
    jwt_token_factory: Callable[[str, str, datetime | None, datetime | None, datetime | None], str],
    gcp_extension: System,
):
    expired_time = datetime.now(UTC) - timedelta(hours=1)
    expired_token = jwt_token_factory(
        str(gcp_extension.id),
        gcp_extension.jwt_secret,
        exp=expired_time,
    )

    response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


# ====================
# Create Entitlements
# ====================


async def test_can_create_entitlements(
    api_client: AsyncClient,
    gcp_jwt_token: str,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        json={
            "sponsor_name": "AWS",
            "sponsor_external_id": "EXTERNAL_ID_987123",
            "sponsor_container_id": "SPONSOR_CONTAINER_ID_1234",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["activated_at"] is None
    assert data["sponsor_name"] == "AWS"
    assert data["sponsor_external_id"] == "EXTERNAL_ID_987123"
    assert data["sponsor_container_id"] == "SPONSOR_CONTAINER_ID_1234"
    assert data["status"] == "new"
    assert data["activated_at"] is None
    assert data["created_at"] is not None
    assert data["created_by"] is not None
    assert data["created_by"]["type"] == "system"
    assert data["updated_by"] is not None
    assert data["updated_by"]["type"] == "system"

    result = await db_session.execute(select(Entitlement).where(Entitlement.id == data["id"]))
    assert result.one_or_none() is not None


async def test_create_entitlement_with_incomplete_data(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.post(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        json={
            "sponsor_name": "AWS",
            "sponsor_external_id": "EXTERNAL_ID_987123",
        },
    )

    assert response.status_code == 422
    [detail] = response.json()["detail"]

    assert detail["type"] == "missing"
    assert detail["loc"] == ["body", "sponsor_container_id"]


# ================
# Get Entitlements
# ================


async def test_get_all_entitlements_empty_db(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


async def test_get_all_entitlements_single_page(
    entitlement_aws, entitlement_gcp, api_client: AsyncClient, gcp_jwt_token: str
):
    response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == data["total"]

    assert_json_contains_model(data, from_orm(EntitlementRead, entitlement_aws))
    assert_json_contains_model(data, from_orm(EntitlementRead, entitlement_gcp))


async def test_get_all_entitlements_multiple_pages(
    entitlement_factory: ModelFactory[Entitlement],
    api_client: AsyncClient,
    gcp_jwt_token: str,
):
    for index in range(10):
        await entitlement_factory(
            sponsor_name="AWS",
            sponsor_external_id=f"EXTERNAL_ID_{index}",
            sponsor_container_id=f"CONTAINER_ID_{index}",
        )

    first_page_response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        params={"limit": 5},
    )
    first_page_data = first_page_response.json()
    assert first_page_response.status_code == 200
    assert first_page_data["total"] == 10
    assert len(first_page_data["items"]) == 5
    assert first_page_data["limit"] == 5
    assert first_page_data["offset"] == 0

    second_page_response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        params={"limit": 3, "offset": 5},
    )
    second_page_data = second_page_response.json()

    assert second_page_response.status_code == 200
    assert second_page_data["total"] == 10
    assert len(second_page_data["items"]) == 3
    assert second_page_data["limit"] == 3
    assert second_page_data["offset"] == 5

    third_page_response = await api_client.get(
        "/entitlements/",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        params={"offset": 8},
    )
    third_page_data = third_page_response.json()

    assert third_page_response.status_code == 200
    assert third_page_data["total"] == 10
    assert len(third_page_data["items"]) == 2
    assert third_page_data["limit"] > 2
    assert third_page_data["offset"] == 8

    all_items = first_page_data["items"] + second_page_data["items"] + third_page_data["items"]
    all_external_ids = {item["sponsor_external_id"] for item in all_items}
    assert len(all_items) == 10
    assert all_external_ids == {f"EXTERNAL_ID_{index}" for index in range(10)}


# =====================
# Get Entitlement by ID
# =====================


async def test_get_entitlement_by_id(entitlement_aws, api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.get(
        f"/entitlements/{entitlement_aws.id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(entitlement_aws.id)
    assert data["sponsor_name"] == entitlement_aws.sponsor_name
    assert data["sponsor_external_id"] == entitlement_aws.sponsor_external_id
    assert data["sponsor_container_id"] == entitlement_aws.sponsor_container_id
    assert data["status"] == "new"
    assert data["activated_at"] is None
    assert data["created_at"] is not None


async def test_get_non_existant_entitlement(api_client: AsyncClient, gcp_jwt_token: str):
    id = str(uuid.uuid4())
    response = await api_client.get(
        f"/entitlements/{id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Entitlement with ID {id} wasn't found"


async def test_get_invalid_id_format(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.get(
        "/entitlements/this-is-not-a-valid-uuid",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 422

    [detail] = response.json()["detail"]
    assert detail["loc"] == ["path", "id"]
    assert detail["type"] == "uuid_parsing"
