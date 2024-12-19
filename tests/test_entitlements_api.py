import uuid

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Entitlement
from app.repositories import EntitlementRepository
from tests.utils import assert_json_contains_model

# ====================
# Create Entitlements
# ====================


async def test_can_create_entitlements(api_client: AsyncClient, db_session: AsyncSession):
    response = await api_client.post(
        "/entitlements/",
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

    result = await db_session.exec(select(Entitlement).where(Entitlement.id == data["id"]))
    assert result.one_or_none() is not None


async def test_create_entitlement_with_incomplete_data(api_client: AsyncClient):
    response = await api_client.post(
        "/entitlements/",
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


async def test_get_all_entitlements_empty_db(api_client: AsyncClient):
    response = await api_client.get("/entitlements/")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


async def test_get_all_entitlements_single_page(
    entitlement_aws, entitlement_gcp, api_client: AsyncClient
):
    response = await api_client.get("/entitlements/")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == data["total"]

    assert_json_contains_model(data, entitlement_aws)
    assert_json_contains_model(data, entitlement_gcp)


async def test_get_all_entitlements_multiple_pages(
    entitlements_repository: EntitlementRepository,
    api_client: AsyncClient,
    fastapi_app,
):
    for index in range(10):
        await entitlements_repository.create(
            Entitlement(
                sponsor_name="AWS",
                sponsor_external_id=f"EXTERNAL_ID_{index}",
                sponsor_container_id=f"CONTAINER_ID_{index}",
            )
        )

    first_page_response = await api_client.get("/entitlements/", params={"limit": 5})
    first_page_data = first_page_response.json()
    assert first_page_response.status_code == 200
    assert first_page_data["total"] == 10
    assert len(first_page_data["items"]) == 5
    assert first_page_data["limit"] == 5
    assert first_page_data["offset"] == 0

    second_page_response = await api_client.get("/entitlements/", params={"limit": 3, "offset": 5})
    second_page_data = second_page_response.json()

    assert second_page_response.status_code == 200
    assert second_page_data["total"] == 10
    assert len(second_page_data["items"]) == 3
    assert second_page_data["limit"] == 3
    assert second_page_data["offset"] == 5

    third_page_response = await api_client.get("/entitlements/", params={"offset": 8})
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


async def test_get_entitlement_by_id(entitlement_aws, api_client: AsyncClient):
    response = await api_client.get(f"/entitlements/{entitlement_aws.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(entitlement_aws.id)
    assert data["sponsor_name"] == entitlement_aws.sponsor_name
    assert data["sponsor_external_id"] == entitlement_aws.sponsor_external_id
    assert data["sponsor_container_id"] == entitlement_aws.sponsor_container_id


async def test_get_non_existant_entitlement(api_client: AsyncClient):
    id = str(uuid.uuid4())
    response = await api_client.get(f"/entitlements/{id}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Entitlement with ID {id} wasn't found"


# ==================
# Update Entitlement
# ==================


async def test_can_update_entitlements(entitlement_aws, api_client):
    assert entitlement_aws.sponsor_name == "AWS"

    update_response = await api_client.patch(
        f"/entitlements/{entitlement_aws.id}",
        json={"sponsor_name": "GCP"},
    )

    assert update_response.status_code == 200
    update_data = update_response.json()

    assert update_data["sponsor_name"] == "GCP"

    get_response = await api_client.get(f"/entitlements/{entitlement_aws.id}")
    assert get_response.json()["sponsor_name"] == "GCP"


async def test_try_update_non_existant_entitlement(api_client: AsyncClient):
    id = str(uuid.uuid4())
    response = await api_client.patch(
        f"/entitlements/{id}",
        json={"sponsor_name": "GCP"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == f"Entitlement with ID {id} wasn't found"


async def test_try_update_entitlement_with_invalid_data(entitlement_aws, api_client: AsyncClient):
    response = await api_client.patch(
        f"/entitlements/{entitlement_aws.id}",
        json={"sponsor_name": "GCP", "sponsor_container_id": 123},
    )

    assert response.status_code == 422
    [detail] = response.json()["detail"]

    assert detail["loc"] == ["body", "sponsor_container_id"]
    assert detail["msg"] == "Input should be a valid string"
