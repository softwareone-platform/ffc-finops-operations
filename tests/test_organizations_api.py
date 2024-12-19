from httpx import AsyncClient

from app.models import Organization
from tests.conftest import SQLModelFactory
from tests.utils import assert_json_contains_model

# =================
# Get Organizations
# =================


async def test_get_all_organizations_empty_db(api_client: AsyncClient):
    response = await api_client.get("/organizations/")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


async def test_get_all_organizations_single_page(
    organization_factory: SQLModelFactory[Organization], api_client: AsyncClient
):
    organization_1 = await organization_factory(external_id="EXTERNAL_ID_1")
    organization_2 = await organization_factory(external_id="EXTERNAL_ID_2")

    response = await api_client.get("/organizations/")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == data["total"]

    assert_json_contains_model(data, organization_1)
    assert_json_contains_model(data, organization_2)


async def test_get_all_organizations_multiple_pages(
    organization_factory: SQLModelFactory[Organization], api_client: AsyncClient
):
    for index in range(10):
        await organization_factory(
            name=f"Organization {index}",
            external_id=f"EXTERNAL_ID_{index}",
        )

    first_page_response = await api_client.get("/organizations/", params={"limit": 5})
    first_page_data = first_page_response.json()

    assert first_page_response.status_code == 200
    assert first_page_data["total"] == 10
    assert len(first_page_data["items"]) == 5
    assert first_page_data["limit"] == 5
    assert first_page_data["offset"] == 0

    second_page_response = await api_client.get("/organizations/", params={"limit": 3, "offset": 5})
    second_page_data = second_page_response.json()

    assert second_page_response.status_code == 200
    assert second_page_data["total"] == 10
    assert len(second_page_data["items"]) == 3
    assert second_page_data["limit"] == 3
    assert second_page_data["offset"] == 5

    third_page_response = await api_client.get("/organizations/", params={"offset": 8})
    third_page_data = third_page_response.json()

    assert third_page_response.status_code == 200
    assert third_page_data["total"] == 10
    assert len(third_page_data["items"]) == 2
    assert third_page_data["limit"] > 2
    assert third_page_data["offset"] == 8

    all_items = first_page_data["items"] + second_page_data["items"] + third_page_data["items"]
    all_external_ids = {item["external_id"] for item in all_items}
    assert len(all_items) == 10
    assert all_external_ids == {f"EXTERNAL_ID_{index}" for index in range(10)}
