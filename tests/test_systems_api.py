from collections.abc import Callable
from datetime import datetime

from httpx import AsyncClient

from app.db.models import Account, System
from app.enums import SystemStatus
from tests.conftest import ModelFactory

# ================
# Get System by ID
# ================


async def test_get_system_by_id(
    gcp_extension: System,
    gcp_jwt_token: str,
    api_client: AsyncClient,
):
    response = await api_client.get(
        f"/systems/{gcp_extension.id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == gcp_extension.id
    assert data["name"] == gcp_extension.name
    assert data["external_id"] == gcp_extension.external_id
    assert data["description"] == gcp_extension.description
    assert data["jwt_secret"] == gcp_extension.jwt_secret
    assert data["owner"]["id"] == gcp_extension.owner_id
    assert datetime.fromisoformat(data["created_at"]) == gcp_extension.created_at
    assert datetime.fromisoformat(data["updated_at"]) == gcp_extension.updated_at
    assert data["deleted_at"] is None
    assert data["deleted_at"] == gcp_extension.deleted_at
    assert data["created_by"] == gcp_extension.created_by
    assert data["updated_by"] == gcp_extension.updated_by
    assert data["deleted_by"] is None
    assert data["status"] == gcp_extension.status._value_


async def test_get_system_by_id_no_auth(
    gcp_extension: System,
    gcp_jwt_token: str,
    api_client: AsyncClient,
):
    response = await api_client.get(f"/systems/{gcp_extension.id}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


async def test_get_system_with_deleted_status(
    api_client: AsyncClient,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
):
    account = await account_factory()
    first_active_system = await system_factory(owner=account, external_id="first-active-system")
    second_active_system = await system_factory(owner=account, external_id="second-active-system")
    deleted_system = await system_factory(
        owner=account, status=SystemStatus.DELETED, external_id="deleted-system"
    )

    response = await api_client.get(
        f"/systems/{second_active_system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(first_active_system)}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == second_active_system.id
    assert data["status"] == "active"

    response = await api_client.get(
        f"/systems/{deleted_system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(first_active_system)}"},
    )

    # Even though a system is marked as deleted, it should still be retrievable
    # This is because the API is used for an admin interface, so the user
    # should be able to see all systems

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == deleted_system.id
    assert data["status"] == "deleted"


async def test_get_system_by_id_auth_different_account(
    api_client: AsyncClient,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
):
    first_acc = await account_factory(name="first-account")
    second_acc = await account_factory(name="second-account")

    first_system = await system_factory(owner=first_acc, external_id="first-system")
    second_system = await system_factory(owner=second_acc, external_id="second-system")

    response = await api_client.get(
        f"/systems/{first_system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(second_system)}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"System with ID `{first_system.id}` wasn't found"


async def test_get_non_existant_system(api_client: AsyncClient, gcp_jwt_token: str):
    id = "FTKN-1234-5678"
    response = await api_client.get(
        f"/systems/{id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"System with ID `{id}` wasn't found"


async def test_get_invalid_id_format(api_client: AsyncClient, gcp_jwt_token: str):
    response = await api_client.get(
        "/systems/this-is-not-a-valid-uuid",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 422

    [detail] = response.json()["detail"]
    assert detail["loc"] == ["path", "id"]
    assert detail["type"] == "string_pattern_mismatch"
