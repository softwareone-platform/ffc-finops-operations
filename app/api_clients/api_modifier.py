import httpx

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient, BearerAuth
from app.utils import get_api_modifier_jwt_token


class APIModifierClientError(APIClientError):
    pass


class APIModifierClient(BaseAPIClient):
    base_url = settings.api_modifier_base_url

    def get_auth(self) -> BearerAuth:
        return BearerAuth(get_api_modifier_jwt_token())

    async def create_user(self, email: str, display_name: str, password: str) -> httpx.Response:
        response = await self.httpx_client.post(
            "/admin/users",
            json={
                "email": email,
                "display_name": display_name,
                "password": password,
            },
        )

        response.raise_for_status()
        return response

    async def create_organization(
        self,
        org_name: str,
        user_id: str,
        currency: str,
    ) -> httpx.Response:
        response = await self.httpx_client.post(
            "/admin/organizations",
            json={
                "org_name": org_name,
                "user_id": user_id,
                "currency": currency,
            },
        )
        response.raise_for_status()
        return response
