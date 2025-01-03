import httpx

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient


class OptscaleClientError(APIClientError):
    pass


class OptscaleClient(BaseAPIClient):
    base_url = settings.opt_api_base_url

    async def reset_password(self, email: str) -> httpx.Response:
        response = await self.httpx_client.post(
            "/restore_password",
            json={"email": email},
        )

        response.raise_for_status()
        return response
