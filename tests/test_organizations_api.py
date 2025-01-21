import uuid

import pytest
from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization, System
from app.schemas import OrganizationRead, from_orm
from tests.conftest import ModelFactory
from tests.utils import assert_json_contains_model

# =================
# Get Organizations
# =================


async def test_get_all_organizations_empty_db(api_client: AsyncClient, ffc_jwt_token: str):
    response = await api_client.get(
        "/organizations/", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


async def test_get_all_organizations_single_page(
    organization_factory: ModelFactory[Organization], api_client: AsyncClient, ffc_jwt_token: str
):
    organization_1 = await organization_factory(external_id="EXTERNAL_ID_1")
    organization_2 = await organization_factory(external_id="EXTERNAL_ID_2")

    response = await api_client.get(
        "/organizations/",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == data["total"]

    assert_json_contains_model(data, from_orm(OrganizationRead, organization_1))
    assert_json_contains_model(data, from_orm(OrganizationRead, organization_2))


async def test_get_all_organizations_multiple_pages(
    organization_factory: ModelFactory[Organization], api_client: AsyncClient, ffc_jwt_token: str
):
    for index in range(10):
        await organization_factory(
            name=f"Organization {index}",
            external_id=f"EXTERNAL_ID_{index}",
        )

    first_page_response = await api_client.get(
        "/organizations/",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        params={"limit": 5},
    )
    first_page_data = first_page_response.json()

    assert first_page_response.status_code == 200
    assert first_page_data["total"] == 10
    assert len(first_page_data["items"]) == 5
    assert first_page_data["limit"] == 5
    assert first_page_data["offset"] == 0

    second_page_response = await api_client.get(
        "/organizations/",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        params={"limit": 3, "offset": 5},
    )
    second_page_data = second_page_response.json()

    assert second_page_response.status_code == 200
    assert second_page_data["total"] == 10
    assert len(second_page_data["items"]) == 3
    assert second_page_data["limit"] == 3
    assert second_page_data["offset"] == 5

    third_page_response = await api_client.get(
        "/organizations/",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        params={"offset": 8},
    )
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


# ====================
# Create Organizations
# ====================


async def test_can_create_organizations(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    db_session: AsyncSession,
    ffc_jwt_token: str,
    ffc_extension: System,
):
    mocker.patch("app.api_clients.base.get_api_modifier_jwt_token", return_value="test_token")

    httpx_mock.add_response(
        method="POST",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        url="https://api-modifier.ffc.com/organizations",
        json={"id": "UUID-yyyy-yyyy-yyyy-yyyy"},
        match_headers={"Authorization": "Bearer test_token"},
    )

    response = await api_client.post(
        "/organizations/",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
        json={
            "name": "My Organization",
            "external_id": "ACC-1234-5678",
            "user_id": "UUID-xxxx-xxxx-xxxx-xxxx",
            "currency": "USD",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["name"] == "My Organization"
    assert data["external_id"] == "ACC-1234-5678"
    assert data["organization_id"] == "UUID-yyyy-yyyy-yyyy-yyyy"
    assert data["created_at"] is not None
    assert data["created_by"]["id"] == str(ffc_extension.id)
    assert data["created_by"]["type"] == ffc_extension.type
    assert data["created_by"]["name"] == ffc_extension.name
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(ffc_extension.id)
    assert data["updated_by"]["type"] == ffc_extension.type
    assert data["updated_by"]["name"] == ffc_extension.name

    result = await db_session.execute(select(Organization).where(Organization.id == data["id"]))
    assert result.one_or_none() is not None


@pytest.mark.parametrize("missing_field", ["name", "external_id", "user_id", "currency"])
async def test_create_organization_with_incomplete_data(
    api_client: AsyncClient, missing_field: str, ffc_jwt_token: str
):
    payload = {
        "name": "My Organization",
        "external_id": "ACC-1234-5678",
        "user_id": "UUID-xxxx-xxxx-xxxx-xxxx",
        "currency": "USD",
    }
    payload.pop(missing_field)

    response = await api_client.post(
        "/organizations/",
        json=payload,
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 422
    [detail] = response.json()["detail"]

    assert detail["type"] == "missing"
    assert detail["loc"] == ["body", missing_field]


async def test_create_organization_with_existing_db_organization(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    organization_factory: ModelFactory[Organization],
    gcp_jwt_token: str,
):
    mocker.patch("app.api_clients.base.get_api_modifier_jwt_token", return_value="test_token")

    existing_org = await organization_factory(external_id="ACC-1234-5678")
    payload = {
        "name": existing_org.name,
        "external_id": "ACC-1234-5678",
        "user_id": "UUID-xxxx-xxxx-xxxx-xxxx",
        "currency": "USD",
    }

    httpx_mock.add_response(
        method="POST",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        url="https://api-modifier.ffc.com/organizations",
        json={"id": "UUID-yyyy-yyyy-yyyy-yyyy"},
        match_headers={"Authorization": "Bearer test_token"},
    )

    response = await api_client.post(
        "/organizations/",
        json=payload,
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 201
    data = response.json()

    assert data["id"] == str(existing_org.id)
    assert data["name"] == existing_org.name
    assert data["external_id"] == "ACC-1234-5678"
    assert data["organization_id"] == "UUID-yyyy-yyyy-yyyy-yyyy"
    assert data["created_at"] is not None


async def test_create_organization_with_existing_db_organization_name_mismatch(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    organization_factory: ModelFactory[Organization],
    ffc_jwt_token: str,
):
    mocker.patch("app.api_clients.base.get_api_modifier_jwt_token", return_value="test_token")

    existing_org = await organization_factory(external_id="ACC-1234-5678")
    payload = {
        "name": f"{existing_org.name} Existing",
        "external_id": "ACC-1234-5678",
        "user_id": "UUID-xxxx-xxxx-xxxx-xxxx",
        "currency": "USD",
    }

    response = await api_client.post(
        "/organizations/",
        json=payload,
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == (
        f"The name of a partially created Organization with "
        f"external ID {existing_org.external_id}  doesn't match the "
        f"current request: {existing_org.name}."
    )


async def test_create_organization_already_created(
    api_client: AsyncClient, organization_factory: ModelFactory[Organization], gcp_jwt_token: str
):
    payload = {
        "name": "My Organization",
        "external_id": "ACC-1234-5678",
        "user_id": "UUID-xxxx-xxxx-xxxx-xxxx",
        "currency": "USD",
    }

    await organization_factory(
        external_id="ACC-1234-5678",
        organization_id="957c9a0a-2d18-4015-b7b0-e1b4259b3167",
    )

    response = await api_client.post(
        "/organizations/",
        json=payload,
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == "An Organization with external ID `ACC-1234-5678` already exists."


async def test_create_organization_api_modifier_error(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.api_clients.base.get_api_modifier_jwt_token", return_value="test_token")

    httpx_mock.add_response(
        method="POST",
        url="https://api-modifier.ffc.com/organizations",
        status_code=500,
        text="Internal Server Error",
    )

    response = await api_client.post(
        "/organizations/",
        json={
            "name": "My Organization",
            "external_id": "ACC-1234-5678",
            "user_id": "UUID-xxxx-xxxx-xxxx-xxxx",
            "currency": "USD",
        },
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 502

    detail = response.json()["detail"]
    assert detail == "Error creating organization in FinOps for Cloud: 500 - Internal Server Error."


# =====================
# Get Organization by ID
# ======================


async def test_get_organization_by_id(
    organization_factory: ModelFactory[Organization],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    ffc_extension: System,
):
    org = await organization_factory(
        created_by=ffc_extension,
        updated_by=ffc_extension,
    )
    response = await api_client.get(
        f"/organizations/{org.id}", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(org.id)
    assert data["name"] == org.name
    assert data["external_id"] == org.external_id
    assert data["created_at"] is not None
    assert data["created_by"]["id"] == str(ffc_extension.id)
    assert data["created_by"]["type"] == ffc_extension.type
    assert data["created_by"]["name"] == ffc_extension.name
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(ffc_extension.id)
    assert data["updated_by"]["type"] == ffc_extension.type
    assert data["updated_by"]["name"] == ffc_extension.name


async def test_get_non_existant_organization(api_client: AsyncClient, ffc_jwt_token: str):
    id = str(uuid.uuid4())
    response = await api_client.get(
        f"/organizations/{id}", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Organization with ID `{id}` wasn't found"


async def test_get_invalid_id_format(api_client: AsyncClient, ffc_jwt_token: str):
    response = await api_client.get(
        "/organizations/this-is-not-a-valid-uuid",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 422

    [detail] = response.json()["detail"]
    assert detail["loc"] == ["path", "organization_id"]
    assert detail["type"] == "uuid_parsing"
