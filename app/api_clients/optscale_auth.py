import httpx

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient, OptscaleClusterSecretAuth
from app.api_clients.constants import OPT_RESOURCE_TYPE_ORGANIZATION, OPT_ROLE_ORGANIZATION_ADMIN


class OptscaleAuthClientError(APIClientError):
    pass


class UserDoesNotExist(OptscaleAuthClientError):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"User with email {email} does not exist")


class OptscaleAuthClient(BaseAPIClient):
    base_url = settings.opt_auth_base_url
    default_auth = OptscaleClusterSecretAuth()

    async def get_existing_user_info(self, email: str) -> httpx.Response:
        response = await self.httpx_client.get(
            "/user_existence",
            params={
                "email": email,
                "user_info": "true",
            },
        )
        response.raise_for_status()
        response_data = response.json()

        if not response_data.get("exists", False):
            raise UserDoesNotExist(email)

        return response

    async def make_user_admin(self, organization_id: str, user_id: str) -> httpx.Response:
        response = await self.httpx_client.post(
            f"/users/{user_id}/assignment_register",
            json={
                "role_id": OPT_ROLE_ORGANIZATION_ADMIN,
                "type_id": OPT_RESOURCE_TYPE_ORGANIZATION,
                "resource_id": organization_id,
            },
        )
        response.raise_for_status()
        return response
