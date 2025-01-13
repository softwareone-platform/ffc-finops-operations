from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entitlement, System
from app.enums import EntitlementStatus
from tests.conftest import JWTTokenFactory, ModelFactory

# ====================
# Authentication Tests
# ====================


async def test_get_entitlements_without_token(api_client: AsyncClient):
    response = await api_client.get("/entitlements")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_get_entitlements_with_invalid_token(api_client: AsyncClient):
    response = await api_client.get(
        "/entitlements",
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
        "/entitlements",
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
    gcp_extension: System,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/entitlements",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        json={
            "name": "AWS",
            "affiliate_external_id": "EXTERNAL_ID_987123",
            "datasource_id": "SPONSOR_CONTAINER_ID_1234",
        },
    )
    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["name"] == "AWS"
    assert data["affiliate_external_id"] == "EXTERNAL_ID_987123"
    assert data["datasource_id"] == "SPONSOR_CONTAINER_ID_1234"
    assert data["status"] == "new"
    assert data["created_at"] is not None
    assert data["created_by"]["id"] == str(gcp_extension.id)
    assert data["created_by"]["type"] == gcp_extension.type
    assert data["created_by"]["name"] == gcp_extension.name
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(gcp_extension.id)
    assert data["updated_by"]["type"] == gcp_extension.type
    assert data["updated_by"]["name"] == gcp_extension.name

    result = await db_session.execute(select(Entitlement).where(Entitlement.id == data["id"]))
    assert result.one_or_none() is not None


async def test_create_entitlement_with_incomplete_data(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.post(
        "/entitlements",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
        json={
            "name": "AWS",
            "affiliate_external_id": "EXTERNAL_ID_987123",
        },
    )

    assert response.status_code == 422
    [detail] = response.json()["detail"]

    assert detail["type"] == "missing"
    assert detail["loc"] == ["body", "datasource_id"]


# ================
# Get Entitlements
# ================


async def test_get_all_entitlements_empty_db(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.get(
        "/entitlements",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


async def test_get_all_entitlements_single_page(
    entitlement_aws, entitlement_gcp, api_client: AsyncClient, gcp_jwt_token: str
):
    response = await api_client.get(
        "/entitlements",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == data["total"]


async def test_get_all_entitlements_multiple_pages(
    entitlement_factory: ModelFactory[Entitlement],
    api_client: AsyncClient,
    gcp_jwt_token: str,
):
    for index in range(10):
        await entitlement_factory(
            name="AWS",
            affiliate_external_id=f"EXTERNAL_ID_{index}",
            datasource_id=f"CONTAINER_ID_{index}",
        )

    first_page_response = await api_client.get(
        "/entitlements",
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
        "/entitlements",
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
        "/entitlements",
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
    all_external_ids = {item["affiliate_external_id"] for item in all_items}
    assert len(all_items) == 10
    assert all_external_ids == {f"EXTERNAL_ID_{index}" for index in range(10)}


# =====================
# Get Entitlement by ID
# =====================


async def test_get_entitlement_by_id(
    entitlement_aws: Entitlement,
    api_client: AsyncClient,
    gcp_jwt_token: str,
    gcp_extension: System,
):
    response = await api_client.get(
        f"/entitlements/{entitlement_aws.id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(entitlement_aws.id)
    assert data["name"] == entitlement_aws.name
    assert data["affiliate_external_id"] == entitlement_aws.affiliate_external_id
    assert data["datasource_id"] == entitlement_aws.datasource_id
    assert data["status"] == "new"
    assert data["created_at"] is not None
    assert data["created_by"]["id"] == str(gcp_extension.id)
    assert data["created_by"]["type"] == gcp_extension.type
    assert data["created_by"]["name"] == gcp_extension.name
    assert data["updated_at"] is not None
    assert data["updated_by"]["id"] == str(gcp_extension.id)
    assert data["updated_by"]["type"] == gcp_extension.type
    assert data["updated_by"]["name"] == gcp_extension.name


async def test_get_non_existant_entitlement(api_client: AsyncClient, gcp_jwt_token: str):
    id = "FENT-1234-5678-9012"
    response = await api_client.get(
        f"/entitlements/{id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Entitlement with ID `{id}` wasn't found"


async def test_get_invalid_id_format(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.get(
        "/entitlements/this-is-not-a-valid-uuid",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 422

    [detail] = response.json()["detail"]
    assert detail["loc"] == ["path", "id"]
    assert detail["type"] == "string_pattern_mismatch"


# =====================
# Terminate Entitlement
# =====================


async def test_terminate_entitlement_success(
    entitlement_aws: Entitlement,
    api_client: AsyncClient,
    gcp_jwt_token: str,
    gcp_extension: System,
    db_session: AsyncSession,
):
    assert entitlement_aws.terminated_at is None
    assert entitlement_aws.terminated_by is None
    assert entitlement_aws.status == EntitlementStatus.NEW

    entitlement_aws.status = EntitlementStatus.ACTIVE

    db_session.add(entitlement_aws)
    await db_session.commit()
    await db_session.refresh(entitlement_aws)

    request_start_dt = datetime.now(UTC)
    response = await api_client.post(
        f"/entitlements/{entitlement_aws.id}/terminate",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )
    request_end_dt = datetime.now(UTC)

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(entitlement_aws.id)
    assert data["status"] == "terminated"

    await db_session.refresh(entitlement_aws)

    assert entitlement_aws.status == EntitlementStatus.TERMINATED
    assert entitlement_aws.terminated_at is not None
    assert request_start_dt < entitlement_aws.terminated_at < request_end_dt
    assert entitlement_aws.terminated_by_id == gcp_extension.id


async def test_terminate_new_entitlement(
    entitlement_aws: Entitlement,
    api_client: AsyncClient,
    gcp_jwt_token: str,
    gcp_extension: System,
):
    assert entitlement_aws.status == EntitlementStatus.NEW

    response = await api_client.post(
        f"/entitlements/{entitlement_aws.id}/terminate",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 400
    error_msg = response.json()["detail"]

    assert error_msg == "Only active entitlements can be terminated, current status is new"


async def test_terminate_already_terminated_entitlement(
    entitlement_aws: Entitlement,
    api_client: AsyncClient,
    gcp_jwt_token: str,
    gcp_extension: System,
    db_session: AsyncSession,
):
    entitlement_aws.status = EntitlementStatus.TERMINATED

    db_session.add(entitlement_aws)
    await db_session.commit()

    response = await api_client.post(
        f"/entitlements/{entitlement_aws.id}/terminate",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 400
    error_msg = response.json()["detail"]

    assert error_msg == "Entitlement is already terminated"


async def test_terminate_non_existant_entitlement(
    api_client: AsyncClient,
    gcp_jwt_token: str,
    gcp_extension: System,
    db_session: AsyncSession,
):
    entitlement_id = "FENT-1234-5678-9012"
    response = await api_client.post(
        f"/entitlements/{entitlement_id}/terminate",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 404
    error_msg = response.json()["detail"]

    assert error_msg == f"Entitlement with ID `{entitlement_id}` wasn't found"
