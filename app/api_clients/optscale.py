from uuid import UUID

import httpx

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient, OptscaleClusterSecretAuth


class OptscaleClientError(APIClientError):
    pass


class OptscaleClient(BaseAPIClient):
    base_url = settings.opt_api_base_url
    default_auth = OptscaleClusterSecretAuth()

    async def reset_password(self, email: str) -> httpx.Response:
        response = await self.httpx_client.post(
            "/restore_password",
            json={"email": email},
            auth=None,
        )

        response.raise_for_status()
        return response

    async def fetch_cloud_accounts_for_organization(
        self, organization_id: UUID | str
    ) -> httpx.Response:
        response = await self.httpx_client.get(
            f"/organizations/{organization_id}/cloud_accounts",
            params={
                "details": "true",
            },
        )
        response.raise_for_status()
        return response

    async def fetch_cloud_account_by_id(self, cloud_account_id: UUID | str) -> httpx.Response:
        response = await self.httpx_client.get(
            f"/cloud_accounts/{cloud_account_id}",
            params={
                "details": "true",
            },
        )
        response.raise_for_status()
        return response

    async def fetch_users_for_organization(self, organization_id: UUID | str) -> httpx.Response:
        response = await self.httpx_client.get(
            f"/organizations/{organization_id}/employees",
            params={
                "roles": "true",
            },
        )
        response.raise_for_status()
        return response
