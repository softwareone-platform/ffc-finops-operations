from collections.abc import Callable
from datetime import datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, System
from app.enums import AccountType, SystemStatus
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


# ===============
# Get all systems
# ===============


async def test_get_all_systems_single_active_record(
    api_client: AsyncClient,
    gcp_extension: System,
    gcp_jwt_token: str,
):
    response = await api_client.get(
        "/systems", headers={"Authorization": f"Bearer {gcp_jwt_token}"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == gcp_extension.id


async def test_get_all_systems_multiple_systems_single_account(
    api_client: AsyncClient,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
):
    account = await account_factory()
    expected_systems = [
        await system_factory(owner=account),
        await system_factory(owner=account),
        await system_factory(owner=account, status=SystemStatus.DISABLED),
        await system_factory(owner=account, status=SystemStatus.DISABLED),
        await system_factory(owner=account),
        await system_factory(owner=account, status=SystemStatus.DELETED),
    ]

    response = await api_client.get(
        "/systems",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(expected_systems[0])}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == len(expected_systems)

    ids = {system["id"] for system in response.json()["items"]}
    assert ids == {system.id for system in expected_systems}


async def test_get_all_systems_multiple_systems_in_different_accounts(
    api_client: AsyncClient,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
):
    first_account = await account_factory()
    second_account = await account_factory()

    expected_systems = [
        await system_factory(owner=first_account),
        await system_factory(owner=first_account),
        await system_factory(owner=first_account, status=SystemStatus.DISABLED),
        await system_factory(owner=first_account, status=SystemStatus.DISABLED),
        await system_factory(owner=first_account),
        await system_factory(owner=first_account, status=SystemStatus.DELETED),
    ]

    await system_factory(owner=second_account)
    await system_factory(owner=second_account, status=SystemStatus.DISABLED)
    await system_factory(owner=second_account, status=SystemStatus.DELETED)

    response = await api_client.get(
        "/systems",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(expected_systems[0])}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == len(expected_systems)

    ids = {system["id"] for system in response.json()["items"]}
    assert ids == {system.id for system in expected_systems}


@pytest.mark.parametrize(
    ("create_systems_count", "limit", "offset", "expected_total", "page_count"),
    [
        (100, None, None, 100, 50),
        (100, 10, None, 100, 10),
        (100, None, 95, 100, 5),
        (100, 10, 95, 100, 5),
        (2, 5, 1, 2, 1),
    ],
)
async def test_get_all_systems_pagination(
    create_systems_count: int,
    limit: int | None,
    offset: int | None,
    expected_total: int,
    page_count: int,
    api_client: AsyncClient,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
):
    account = await account_factory()

    for _ in range(create_systems_count):
        system = await system_factory(owner=account)

    params = {}

    if limit is not None:
        params["limit"] = limit

    if offset is not None:
        params["offset"] = offset

    response = await api_client.get(
        "/systems",
        params=params,
        headers={"Authorization": f"Bearer {system_jwt_token_factory(system)}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == expected_total
    assert len(response.json()["items"]) == page_count


async def test_get_systems_with_operations_api(
    api_client: AsyncClient,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
):
    operations_account = await account_factory(type=AccountType.OPERATIONS)
    operations_system = await system_factory(owner=operations_account)

    affilaite_account = await account_factory(type=AccountType.AFFILIATE)
    affiliate_system = await system_factory(owner=affilaite_account)

    response = await api_client.get(
        "/systems",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(operations_system)}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert {system["id"] for system in data["items"]} == {operations_system.id, affiliate_system.id}


# ==============
# Disable system
# ==============


@pytest.mark.parametrize(
    (
        "initial_status",
        "expected_status_code",
        "expected_new_status",
    ),
    [
        pytest.param(
            SystemStatus.ACTIVE,
            status.HTTP_200_OK,
            SystemStatus.DISABLED,
            id="disable_active",
        ),
        pytest.param(
            SystemStatus.DISABLED,
            status.HTTP_400_BAD_REQUEST,
            SystemStatus.DISABLED,
            id="disable_disabled_fail",
        ),
        pytest.param(
            SystemStatus.DELETED,
            status.HTTP_400_BAD_REQUEST,
            SystemStatus.DELETED,
            id="disable_deleted_fail",
        ),
    ],
)
async def test_disable_system(
    initial_status: SystemStatus,
    expected_status_code: int,
    expected_new_status: SystemStatus,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    ffc_extension: System,
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    system = await system_factory(status=initial_status)

    response = await api_client.post(
        f"/systems/{system.id}/disable",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
    )

    assert response.status_code == expected_status_code

    if response.is_error:
        expected_error_msg = (
            f"System's status is '{initial_status._value_}'; only active systems can be disabled."
        )
        assert response.json()["detail"] == expected_error_msg
    else:
        data = response.json()
        assert data["status"] == expected_new_status._value_

    await db_session.refresh(system)
    assert system.status == expected_new_status


async def test_system_cannot_disable_itself(
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    system = await system_factory(status=SystemStatus.ACTIVE)

    response = await api_client.post(
        f"/systems/{system.id}/disable",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(system)}"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "A system cannot disable itself."

    # Verify the system's status hasn't changed
    await db_session.refresh(system)
    assert system.status == SystemStatus.ACTIVE


# =============
# Enable system
# =============


@pytest.mark.parametrize(
    (
        "initial_status",
        "expected_status_code",
        "expected_new_status",
    ),
    [
        pytest.param(
            SystemStatus.DISABLED,
            status.HTTP_200_OK,
            SystemStatus.ACTIVE,
            id="enable_disabled",
        ),
        pytest.param(
            SystemStatus.ACTIVE,
            status.HTTP_400_BAD_REQUEST,
            SystemStatus.ACTIVE,
            id="enable_active_fail",
        ),
        pytest.param(
            SystemStatus.DELETED,
            status.HTTP_400_BAD_REQUEST,
            SystemStatus.DELETED,
            id="enable_deleted_fail",
        ),
    ],
)
async def test_enable_system(
    initial_status: SystemStatus,
    expected_status_code: int,
    expected_new_status: SystemStatus,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    ffc_extension: System,
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    system = await system_factory(status=initial_status)

    response = await api_client.post(
        f"/systems/{system.id}/enable",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
    )

    assert response.status_code == expected_status_code

    if response.is_error:
        expected_error_msg = (
            f"System's status is '{initial_status._value_}'; only disabled systems can be enabled."
        )
        assert response.json()["detail"] == expected_error_msg
    else:
        data = response.json()
        assert data["status"] == expected_new_status._value_

    await db_session.refresh(system)
    assert system.status == expected_new_status


async def test_system_cannot_enable_itself(
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    system = await system_factory(status=SystemStatus.DISABLED)

    response = await api_client.post(
        f"/systems/{system.id}/enable",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(system)}"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Unauthorized"

    await db_session.refresh(system)
    assert system.status == SystemStatus.DISABLED
