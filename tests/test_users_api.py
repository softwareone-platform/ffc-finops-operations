import uuid

from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from app import settings
from app.db.models import Organization
from tests.conftest import ModelFactory


async def test_can_create_users(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.api_clients.base.get_api_modifier_jwt_token", return_value="test_token")
    mocked_token_urlsafe = mocker.patch(
        "app.routers.users.secrets.token_urlsafe", return_value="random_password"
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api-modifier.ffc.com/users",
        match_json={
            "email": "test@example.com",
            "display_name": "Test User",
            "password": "random_password",
        },
        json={
            "id": "1bf6f063-d90b-4d45-8e7f-62fefa9f5471",
            "email": "test@example.com",
            "display_name": "Test User",
            "created_at": 1736929940,
        },
        match_headers={"Authorization": "Bearer test_token"},
    )

    httpx_mock.add_response(
        method="POST",
        url="https://opt-api.ffc.com/restore_password",
        match_json={"email": "test@example.com"},
        json={
            "status": "ok",
            "email": "example@email.com",
        },
    )

    response = await api_client.post(
        "/users/",
        json={"email": "test@example.com", "display_name": "Test User"},
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )
    assert response.status_code == 201
    assert response.json() == {
        "id": "1bf6f063-d90b-4d45-8e7f-62fefa9f5471",
        "email": "test@example.com",
        "display_name": "Test User",
        "created_at": "2025-01-15T08:32:20Z",
        "last_login": None,
        "roles_count": None,
    }

    mocked_token_urlsafe.assert_called_once_with(128)


async def test_create_user_error_creating_user(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.api_clients.base.get_api_modifier_jwt_token", return_value="test_token")

    httpx_mock.add_response(
        method="POST",
        url="https://api-modifier.ffc.com/users",
        status_code=500,
        text="Internal Server Error",
    )

    response = await api_client.post(
        "/users/",
        json={"email": "test@example.com", "display_name": "Test User"},
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )
    assert response.status_code == 502
    assert response.json() == {
        "detail": "Error creating user in FinOps for Cloud: 500 - Internal Server Error.",
    }


async def test_get_user_by_email(
    httpx_mock: HTTPXMock, api_client: AsyncClient, ffc_jwt_token: str
):
    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        json={
            "exists": True,
            "user_info": {
                "id": "1bf6f063-d90b-4d45-8e7f-62fefa9f5471",
                "email": "test@example.com",
                "display_name": "Test User",
                "created_at": 1731059464,
            },
        },
        match_headers={"Secret": settings.opt_cluster_secret},
    )

    response = await api_client.get(
        "/users/test@example.com",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "1bf6f063-d90b-4d45-8e7f-62fefa9f5471",
        "email": "test@example.com",
        "display_name": "Test User",
        "created_at": "2024-11-08T09:51:04Z",
        "last_login": None,
        "roles_count": None,
    }


async def test_get_user_by_email_not_found(
    httpx_mock: HTTPXMock, api_client: AsyncClient, ffc_jwt_token: str
):
    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        json={
            "exists": False,
        },
        match_headers={"Secret": settings.opt_cluster_secret},
    )

    response = await api_client.get(
        "/users/test@example.com",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "A user with the email `test@example.com` wasn't found.",
    }


async def test_get_user_by_email_lookup_error(
    httpx_mock: HTTPXMock, api_client: AsyncClient, ffc_jwt_token: str
):
    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        status_code=500,
        text="Internal Server Error",
        match_headers={"Secret": settings.opt_cluster_secret},
    )

    response = await api_client.get(
        "/users/test@example.com",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Error checking user existence in FinOps for Cloud: 500 - Internal Server Error.",
    }


# =============================================
# Get users within an organization
# =============================================


async def test_get_users_for_organization_success(
    organization_factory: ModelFactory[Organization],
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    authenticated_client: AsyncClient,
):
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/organizations/{org.organization_id}/employees?roles=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        json={
            "employees": [
                {
                    "deleted_at": 0,
                    "id": "85a86112-a94f-4470-9343-f7d19101b15d",
                    "created_at": 1730390070,
                    "name": "Tim",
                    "organization_id": org.organization_id,
                    "auth_user_id": "989d185b-8c95-4104-b152-36148743e52d",
                    "default_ssh_key_id": None,
                    "slack_connected": False,
                    "jira_connected": False,
                    "last_login": 1730389262,
                    "user_display_name": "Tim",
                    "user_email": "tim.cook@apple.com",
                    "assignments": [],
                },
                {
                    "deleted_at": 0,
                    "id": "0ae68497-a912-4fc1-a559-6f52a99bf12b",
                    "created_at": 1736339978,
                    "name": "Test User",
                    "organization_id": org.organization_id,
                    "auth_user_id": "c391517d-5c71-4195-82cf-47e7e44c06b1",
                    "default_ssh_key_id": None,
                    "slack_connected": False,
                    "jira_connected": False,
                    "last_login": 1737388179,
                    "user_display_name": "Test User",
                    "user_email": "FinOpsTest1@outlook.com",
                    "assignments": [
                        {
                            "assignment_resource_id": "9044af7f-2f62-40cd-976f-1cbbbf1a0411",
                            "role_name": "Manager",
                            "assignment_resource_name": "Apple Inc",
                            "assignment_resource_type": "organization",
                            "assignment_resource_purpose": "business_unit",
                            "assignment_id": "265b6597-d7f6-4de7-8afd-c3ab3c14bf66",
                            "purpose": "optscale_manager",
                        }
                    ],
                },
            ]
        },
    )

    response = await authenticated_client.get(
        f"/organizations/{org.id}/users",
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    assert data == [
        {
            "created_at": "2024-10-31T15:54:30Z",
            "display_name": "Tim",
            "email": "tim.cook@apple.com",
            "id": "85a86112-a94f-4470-9343-f7d19101b15d",
            "last_login": "2024-10-31T15:41:02Z",
            "roles_count": 0,
        },
        {
            "created_at": "2025-01-08T12:39:38Z",
            "display_name": "Test User",
            "email": "FinOpsTest1@outlook.com",
            "id": "0ae68497-a912-4fc1-a559-6f52a99bf12b",
            "last_login": "2025-01-20T15:49:39Z",
            "roles_count": 1,
        },
    ]


async def test_get_users_for_missing_organization(
    authenticated_client: AsyncClient,
):
    org_id = "FORG-1234-5678-9012"
    response = await authenticated_client.get(
        f"/organizations/{org_id}/users",
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"Organization with ID `{org_id}` wasn't found"}


async def test_get_users_for_organization_with_no_users(
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    httpx_mock: HTTPXMock,
):
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/organizations/{org.organization_id}/employees?roles=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        json={"employees": []},
    )

    response = await authenticated_client.get(
        f"/organizations/{org.id}/users",
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_get_users_for_organization_with_no_organization_id(
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    httpx_mock: HTTPXMock,
):
    org = await organization_factory(
        organization_id=None,
    )

    response = await authenticated_client.get(
        f"/organizations/{org.id}/users",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": f"Organization {org.name} has no associated FinOps for Cloud organization"
    }


async def test_get_users_for_organization_with_optscale_error(
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    httpx_mock: HTTPXMock,
):
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/organizations/{org.organization_id}/employees?roles=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        status_code=500,
    )

    response = await authenticated_client.get(
        f"/organizations/{org.id}/users",
    )

    assert response.status_code == 502
    assert f"Error fetching users for organization {org.name}" in response.json()["detail"]


# ===============
# Make user admin
# ===============


async def test_make_user_admin(
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    httpx_mock: HTTPXMock,
):
    user_id = str(uuid.uuid4())
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )
    auth_user_id = str(uuid.uuid4())

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/employees/{user_id}?roles=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        status_code=200,
        json={
            "deleted_at": 0,
            "id": "2c2e9705-8023-437c-b09d-8cbd49f0a682",
            "created_at": 1729156673,
            "name": "Ciccio",
            "organization_id": org.organization_id,
            "auth_user_id": auth_user_id,
            "default_ssh_key_id": None,
        },
    )

    httpx_mock.add_response(
        method="POST",
        url=f"{settings.opt_auth_base_url}/users/{auth_user_id}/assignment_register",
        match_headers={"Secret": settings.opt_cluster_secret},
        status_code=200,
        json={
            "created_at": 1736352461,
            "deleted_at": 0,
            "id": "7884c0c0-be5c-4cc7-8413-dd8033b1e4a2",
            "type_id": 2,
            "role_id": 3,
            "user_id": auth_user_id,
            "resource_id": org.organization_id,
        },
        match_json={
            "role_id": 3,  # Admin
            "type_id": 2,  # Organization
            "resource_id": org.organization_id,
        },
    )
    response = await authenticated_client.post(
        f"/organizations/{org.id}/users/{user_id}/make-admin",
    )
    assert response.status_code == 204


async def test_make_user_admin_not_found(
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    httpx_mock: HTTPXMock,
):
    user_id = str(uuid.uuid4())
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/employees/{user_id}?roles=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        status_code=404,
    )

    response = await authenticated_client.post(
        f"/organizations/{org.id}/users/{user_id}/make-admin",
    )
    assert response.status_code == 502
    assert "Error making user admin in FinOps for Cloud: 404" in response.json()["detail"]


async def test_make_user_admin_error_assigning_role(
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    httpx_mock: HTTPXMock,
):
    user_id = str(uuid.uuid4())
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )
    auth_user_id = str(uuid.uuid4())

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/employees/{user_id}?roles=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        status_code=200,
        json={
            "deleted_at": 0,
            "id": "2c2e9705-8023-437c-b09d-8cbd49f0a682",
            "created_at": 1729156673,
            "name": "Ciccio",
            "organization_id": org.organization_id,
            "auth_user_id": auth_user_id,
            "default_ssh_key_id": None,
        },
    )

    httpx_mock.add_response(
        method="POST",
        url=f"{settings.opt_auth_base_url}/users/{auth_user_id}/assignment_register",
        match_headers={"Secret": settings.opt_cluster_secret},
        status_code=400,
        match_json={
            "role_id": 3,  # Admin
            "type_id": 2,  # Organization
            "resource_id": org.organization_id,
        },
    )
    response = await authenticated_client.post(
        f"/organizations/{org.id}/users/{user_id}/make-admin",
    )
    assert response.status_code == 502
    assert "Error making user admin in FinOps for Cloud: 400" in response.json()["detail"]
