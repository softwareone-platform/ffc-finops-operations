import httpx

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient, ClusterSecretAuth


class OptscaleAuthClientError(APIClientError):
    pass


class UserDoesNotExist(OptscaleAuthClientError):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"User with email {email} does not exist")


class OptscaleAuthClient(BaseAPIClient):
    base_url = settings.opt_auth_base_url
    default_auth = ClusterSecretAuth()

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
