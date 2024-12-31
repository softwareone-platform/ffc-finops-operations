from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from app import settings


async def test_can_create_users(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.routers.users.get_api_modifier_jwt_token", return_value="test_token")
    mocked_token_urlsafe = mocker.patch(
        "app.routers.users.secrets.token_urlsafe", return_value="random_password"
    )

    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        json={"exists": False},
        match_headers={"Secret": settings.opt_cluster_secret},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api-modifier.ffc.com/admin/users",
        match_json={
            "email": "test@example.com",
            "display_name": "Test User",
            "password": "random_password",
        },
        json={
            "id": "1bf6f063-d90b-4d45-8e7f-62fefa9f5471",
            "email": "test@example.com",
            "display_name": "Test User",
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
    }

    mocked_token_urlsafe.assert_called_once_with(128)


async def test_create_user_already_exists(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.routers.users.get_api_modifier_jwt_token", return_value="test_token")

    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        json={
            "exists": True,
            "user_info": {
                "id": "1bf6f063-d90b-4d45-8e7f-62fefa9f5471",
                "email": "test@example.com",
                "display_name": "Test User",
                "created_at": 13234,
            },
        },
        match_headers={"Secret": settings.opt_cluster_secret},
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
    }


async def test_create_user_check_existence_error(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.routers.users.get_api_modifier_jwt_token", return_value="test_token")

    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        status_code=500,
        text="Internal Server Error",
        match_headers={"Secret": settings.opt_cluster_secret},
    )

    response = await api_client.post(
        "/users/",
        json={"email": "test@example.com", "display_name": "Test User"},
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )
    assert response.status_code == 502
    assert response.json() == {
        "detail": [
            "Error checking user existence in FinOps for Cloud: 500 - Internal Server Error.",
        ],
    }


async def test_create_user_error_creating_user(
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    api_client: AsyncClient,
    ffc_jwt_token: str,
):
    mocker.patch("app.routers.users.get_api_modifier_jwt_token", return_value="test_token")

    httpx_mock.add_response(
        method="GET",
        url="https://opt-auth.ffc.com/user_existence?email=test@example.com&user_info=true",
        json={"exists": False},
        match_headers={"Secret": settings.opt_cluster_secret},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api-modifier.ffc.com/admin/users",
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
        "detail": [
            "Error creating user in FinOps for Cloud: 500 - Internal Server Error.",
        ],
    }
