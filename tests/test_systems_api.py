from collections.abc import Callable
from datetime import datetime
from typing import Literal

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
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
    assert data["owner"]["id"] == gcp_extension.owner_id
    assert datetime.fromisoformat(data["created_at"]) == gcp_extension.created_at
    assert datetime.fromisoformat(data["updated_at"]) == gcp_extension.updated_at
    assert data["deleted_at"] is None
    assert data["deleted_at"] == gcp_extension.deleted_at
    assert data["created_by"] == gcp_extension.created_by
    assert data["updated_by"] == gcp_extension.updated_by
    assert data["deleted_by"] is None
    assert data["status"] == gcp_extension.status._value_

    assert "jwt_secret" not in data


async def test_get_system_by_id_no_auth(
    gcp_extension: System,
    gcp_jwt_token: str,
    api_client: AsyncClient,
):
    response = await api_client.get(f"/systems/{gcp_extension.id}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized."


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

    assert "jwt_secret" not in data

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

    assert "jwt_secret" not in data


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
    assert response.json()["detail"] == f"System with ID `{first_system.id}` wasn't found."


async def test_get_non_existant_system(api_client: AsyncClient, gcp_jwt_token: str):
    id = "FTKN-1234-5678"
    response = await api_client.get(
        f"/systems/{id}",
        headers={"Authorization": f"Bearer {gcp_jwt_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"System with ID `{id}` wasn't found."


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

    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["id"] == gcp_extension.id

    assert "jwt_secret" not in data["items"][0]


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
        assert "jwt_secret" not in data

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
        assert "jwt_secret" not in data

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
    assert response.json()["detail"] == "Unauthorized."

    await db_session.refresh(system)
    assert system.status == SystemStatus.DISABLED


# =============
# Delete system
# =============


@pytest.mark.parametrize(
    ("initial_status", "expected_status_code"),
    [
        pytest.param(SystemStatus.DISABLED, status.HTTP_204_NO_CONTENT, id="delete_disabled"),
        pytest.param(SystemStatus.ACTIVE, status.HTTP_204_NO_CONTENT, id="delete_active"),
        pytest.param(SystemStatus.DELETED, status.HTTP_400_BAD_REQUEST, id="delete_deleted_fail"),
    ],
)
async def test_delete_system(
    initial_status: SystemStatus,
    expected_status_code: int,
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    ffc_extension: System,
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    system = await system_factory(status=initial_status)

    response = await api_client.delete(
        f"/systems/{system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
    )

    assert response.status_code == expected_status_code
    await db_session.refresh(system)

    if response.is_error:
        expected_error_msg = "System is already deleted."
        assert response.json()["detail"] == expected_error_msg
        assert system.deleted_at is None
        assert system.deleted_by is None
    else:
        assert not response.content

        assert system.status == SystemStatus.DELETED
        assert system.deleted_at is not None
        assert system.deleted_by is ffc_extension


async def test_system_cannot_delete_itself(
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
):
    system = await system_factory(status=SystemStatus.ACTIVE)

    response = await api_client.delete(
        f"/systems/{system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(system)}"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "A system cannot delete itself."

    # Verify the system's status hasn't changed
    await db_session.refresh(system)
    assert system.status == SystemStatus.ACTIVE


# =============
# Update system
# =============


@pytest.mark.parametrize(
    (
        "update_data",
        "expected_status_code",
        "expected_name",
        "expected_description",
        "expected_external_id",
    ),
    [
        pytest.param(
            {"name": "new_system_name"},
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "initial_name",
            None,
            "initial_external_id",
            id="missing_description_and_external_id",
        ),
        pytest.param(
            {"name": "new_system_name", "external_id": "new_external_id"},
            status.HTTP_200_OK,
            "new_system_name",
            None,
            "new_external_id",
            id="missing_description",
        ),
        pytest.param(
            {"name": "initial_name", "description": None, "external_id": "new_external_id"},
            status.HTTP_200_OK,
            "initial_name",
            None,
            "new_external_id",
            id="update_external_id_only",
        ),
        pytest.param(
            {
                "name": "new_name",
                "description": "new_description",
                "external_id": "new_external_id",
            },
            status.HTTP_200_OK,
            "new_name",
            "new_description",
            "new_external_id",
            id="update_all_fields",
        ),
        pytest.param(
            {
                "name": None,
                "external_id": "new_external_id",
                "description": "new_description",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "initial_name",
            None,
            "initial_external_id",
            id="attempt_to_set_name_to_none",
        ),
        pytest.param(
            {
                "non_existant_field": None,
                "name": "new_name",
                "description": "new_description",
                "external_id": "new_external_id",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "initial_name",
            None,
            "initial_external_id",
            id="attempt_to_set_non_existant_field",
        ),
        pytest.param(
            {
                "name": "new_name",
                "description": "new_description" * 1000,
                "external_id": "new_external_id",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "initial_name",
            None,
            "initial_external_id",
            id="attempt_to_set_description_too_long",
        ),
        pytest.param(
            {
                "name": "new_name",
                "external_id": "new_external_id" * 1000,
                "description": "new_description",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "initial_name",
            None,
            "initial_external_id",
            id="attempt_to_set_external_id_too_long",
        ),
    ],
)
async def test_update_system(
    ffc_extension: System,
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
    update_data: dict[str, str | None],
    expected_status_code: int,
    expected_name: str,
    expected_description: str | None,
    expected_external_id: str,
):
    system = await system_factory(
        name="initial_name",
        external_id="initial_external_id",
        status=SystemStatus.ACTIVE,
    )

    response = await api_client.put(
        f"/systems/{system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
        json=update_data,
    )

    assert response.status_code == expected_status_code

    response_data = response.json()

    if not response.is_error:
        assert response_data["id"] == system.id
        assert response_data["name"] == expected_name
        assert response_data["description"] == expected_description
        assert response_data["external_id"] == expected_external_id

        assert "jwt_secret" not in response_data

    await db_session.refresh(system)

    assert system.name == expected_name
    assert system.description == expected_description
    assert system.external_id == expected_external_id


@pytest.mark.parametrize(
    ("system_to_update_status", "existing_system_status", "expected_status_code"),
    [
        pytest.param(SystemStatus.ACTIVE, SystemStatus.ACTIVE, status.HTTP_400_BAD_REQUEST),
        pytest.param(SystemStatus.ACTIVE, SystemStatus.DISABLED, status.HTTP_400_BAD_REQUEST),
        pytest.param(SystemStatus.DISABLED, SystemStatus.DISABLED, status.HTTP_400_BAD_REQUEST),
        pytest.param(SystemStatus.ACTIVE, SystemStatus.DELETED, status.HTTP_200_OK),
        pytest.param(SystemStatus.DELETED, SystemStatus.ACTIVE, status.HTTP_200_OK),
        pytest.param(SystemStatus.DELETED, SystemStatus.DELETED, status.HTTP_200_OK),
    ],
)
async def test_system_external_id_is_unique_for_non_deleted_objects(
    ffc_extension: System,
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
    system_to_update_status: SystemStatus,
    existing_system_status: SystemStatus,
    expected_status_code: int,
):
    system = await system_factory(
        name="initial_name",
        external_id="initial_external_id",
        status=system_to_update_status,
    )

    # creating another system to test the external_id uniqueness
    await system_factory(
        external_id="existing_external_id",
        status=existing_system_status,
    )
    response = await api_client.put(
        f"/systems/{system.id}",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
        json={
            "name": "initial_name",
            "description": "initial_description",
            "external_id": "existing_external_id",
        },
    )

    assert response.status_code == expected_status_code
    response_data = response.json()

    await db_session.refresh(system)

    if expected_status_code == status.HTTP_200_OK:
        assert "jwt_secret" not in response_data
        assert response_data["external_id"] == "existing_external_id"
        assert system.external_id == "existing_external_id"
    else:
        assert response_data["detail"] == "A system with the same external ID already exists."
        assert system.external_id == "initial_external_id"


# =============
# Create system
# =============


@pytest.mark.parametrize(
    (
        "input_data",
        "expected_status_code",
        "expected_errors",
    ),
    [
        pytest.param(
            {
                "name": "test system",
                "external_id": "test-system",
                "jwt_secret": "eowlqbNqQiKVudOJ-x-nHE1MNQphe3llEzqCOR5FgnPgJj4gLIqD6utRB9qI-Lw64tR1_f3QEhoyJiyz1rsXAg",  # noqa: E501
                "description": "test description",
            },
            status.HTTP_201_CREATED,
            None,
            id="create_basic_with_all_fields",
        ),
        pytest.param(
            {
                "name": "test system",
                "external_id": "test-system",
                "description": "test description",
            },
            status.HTTP_201_CREATED,
            None,
            id="create_with_autogenerated_jwt_secret",
        ),
        pytest.param(
            {
                "name": "test system",
                "external_id": "test-system",
                "description": "test description",
                "owner": {"id": "FACC-MISSING-ID"},
            },
            status.HTTP_400_BAD_REQUEST,
            "The owner account does not exist.",
            id="missing_owner_in_db",
        ),
        pytest.param(
            {
                "name": "test system",
                "external_id": "test-system",
                "jwt_secret": "too-short",
                "description": "test description",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            [("jwt_secret", "String should have at least 64 characters")],
            id="invalid_jwt_secret_length",
        ),
        pytest.param(
            {
                "jwt_secret": None,
                "description": "test description",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            [
                ("name", "Field required"),
                ("external_id", "Field required"),
            ],
            id="missing_name_and_external_id",
        ),
    ],
)
async def test_create_system_by_operations_account(
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
    ffc_extension: System,
    input_data: dict,
    expected_status_code: int,
    expected_errors: list[tuple[str, str]] | str | None,
):
    if "owner" not in input_data:
        input_data["owner"] = {"id": ffc_extension.owner_id}

    response = await api_client.post(
        "/systems",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
        json=input_data,
    )

    assert response.status_code == expected_status_code
    response_data = response.json()

    if response.is_error:
        assert expected_errors is not None

        if isinstance(expected_errors, str):
            assert response_data["detail"] == expected_errors
        else:
            actual_errors = {(err["loc"][-1], err["msg"]) for err in response_data["detail"]}
            assert actual_errors == set(expected_errors)

        created_systems = await db_session.scalar(
            select(select(System).where(System.id != ffc_extension.id).exists())
        )
        assert not created_systems
    else:
        assert expected_errors is None

        db_system = await db_session.get(System, response_data["id"])

        assert response_data["name"] == input_data["name"] == db_system.name
        assert response_data["external_id"] == input_data["external_id"] == db_system.external_id
        assert response_data["status"] == "active" == db_system.status._value_

        if "description" in input_data:
            assert (
                response_data["description"] == input_data["description"] == db_system.description
            )
        else:
            assert response_data["description"] is None
            assert db_system.description is None

        assert "jwt_secret" in response_data

        if "jwt_secret" in input_data:
            assert response_data["jwt_secret"] == input_data["jwt_secret"] == db_system.jwt_secret
        else:
            assert len(response_data["jwt_secret"]) >= 64
            assert response_data["jwt_secret"] == db_system.jwt_secret

        assert response_data["owner"]["id"] == str(ffc_extension.owner_id)
        assert response_data["owner"]["id"] == db_system.owner_id


@pytest.mark.parametrize(
    (
        "creator_account_type",
        "owner_account",
        "expected_status_code",
    ),
    [
        (AccountType.OPERATIONS, None, status.HTTP_400_BAD_REQUEST),
        (AccountType.OPERATIONS, "self", status.HTTP_201_CREATED),
        (AccountType.OPERATIONS, "affiliate", status.HTTP_201_CREATED),
        (AccountType.OPERATIONS, "operations", status.HTTP_201_CREATED),
        (AccountType.AFFILIATE, None, status.HTTP_201_CREATED),
        (AccountType.AFFILIATE, "self", status.HTTP_400_BAD_REQUEST),
        (AccountType.AFFILIATE, "affiliate", status.HTTP_400_BAD_REQUEST),
        (AccountType.AFFILIATE, "operations", status.HTTP_400_BAD_REQUEST),
    ],
)
async def test_create_system_with_different_owners(
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    api_client: AsyncClient,
    db_session: AsyncSession,
    creator_account_type: AccountType,
    owner_account: Literal["self", "affiliate", "operations"] | None,
    expected_status_code: int,
):
    creator_account = await account_factory(type=creator_account_type)
    creator_system = await system_factory(owner=creator_account)
    affiliate_account = await account_factory(type=AccountType.AFFILIATE)
    operations_account = await account_factory(type=AccountType.OPERATIONS)

    if owner_account is None:
        owner_json_field = {}
    elif owner_account == "self":
        owner_json_field = {"owner": {"id": creator_account.id}}
    elif owner_account == "affiliate":
        owner_json_field = {"owner": {"id": affiliate_account.id}}
    elif owner_account == "operations":
        owner_json_field = {"owner": {"id": operations_account.id}}
    else:
        raise RuntimeError("invalid branch")

    response = await api_client.post(
        "/systems",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(creator_system)}"},
        json={
            "name": "test system",
            "external_id": "test-system",
            "description": "test description",
            **owner_json_field,
        },
    )

    assert response.status_code == expected_status_code

    if not response.is_error:
        assert "jwt_secret" in response.json()


@pytest.mark.parametrize(
    ("existing_system_status", "expected_status_code"),
    [
        pytest.param(SystemStatus.ACTIVE, status.HTTP_400_BAD_REQUEST),
        pytest.param(SystemStatus.DISABLED, status.HTTP_400_BAD_REQUEST),
        pytest.param(SystemStatus.DELETED, status.HTTP_201_CREATED),
    ],
)
async def test_create_system_duplicate_external_id_with_deleted(
    account_factory: ModelFactory[Account],
    system_factory: ModelFactory[System],
    system_jwt_token_factory: Callable[[System], str],
    ffc_extension: System,
    api_client: AsyncClient,
    db_session: AsyncSession,
    existing_system_status: SystemStatus,
    expected_status_code: int,
):
    await system_factory(external_id="existing_external_id", status=existing_system_status)

    # Attempt to create a new system with the same external_id
    response = await api_client.post(
        "/systems",
        headers={"Authorization": f"Bearer {system_jwt_token_factory(ffc_extension)}"},
        json={
            "name": "New System",
            "external_id": "existing_external_id",
            "owner": {"id": ffc_extension.owner_id},
        },
    )

    assert response.status_code == expected_status_code
    response_data = response.json()

    created_system = await db_session.scalar(
        select(System).where(System.name == "New System").limit(1)
    )

    if response.is_error:
        assert response_data["detail"] == "A system with the same external ID already exists."
        assert created_system is None
    else:
        assert response_data["external_id"] == "existing_external_id"
        assert created_system.external_id == "existing_external_id"
        assert "jwt_secret" in response_data
