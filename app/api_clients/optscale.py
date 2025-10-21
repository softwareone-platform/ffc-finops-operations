from collections.abc import Generator
from uuid import UUID

import httpx

from app.api_clients.base import APIClientError, BaseAPIClient
from app.conf import Settings

OPT_RESOURCE_TYPE_ORGANIZATION = 2
OPT_ROLE_ORGANIZATION_ADMIN = 3


class OptscaleClientError(APIClientError):
    pass


class OptscaleAuthClientError(APIClientError):
    pass


class UserDoesNotExist(OptscaleAuthClientError):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"User with email {email} does not exist")


class OptscaleClusterSecretAuth(httpx.Auth):
    def __init__(self, settings: Settings):
        self.settings = settings

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Secret"] = self.settings.optscale_cluster_secret

        yield request


class OptscaleClient(BaseAPIClient):
    @property
    def base_url(self):
        return self.settings.optscale_rest_api_base_url

    @property
    def auth(self):
        return OptscaleClusterSecretAuth(self.settings)

    async def reset_password(self, email: str) -> httpx.Response:
        response = await self.httpx_client.post(
            "/restore_password",
            json={"email": email},
            auth=None,  # type: ignore
        )

        response.raise_for_status()
        return response

    async def fetch_datasources_for_organization(
        self, organization_id: UUID | str, details: bool = True
    ) -> httpx.Response:
        response = await self.httpx_client.get(
            f"/organizations/{organization_id}/cloud_accounts",
            params={
                "details": "true" if details else "false",
            },
        )
        response.raise_for_status()
        return response

    async def fetch_daily_expenses_for_organization(
        self, organization_id: UUID | str, start_period: int, end_period: int
    ) -> httpx.Response:
        """
        Retrieves daily non-zero datasource expenses for the specified organization.
        The response includes the total non-zero consumption per datasource within the given period,
        along with a daily cost breakdown.

        Parameters:
        - organization_id (UUID | str): The target organization id.
        - start_period (int): Start of the time range (Unix timestamp, inclusive).
        - end_period (int): End of the time range (Unix timestamp, inclusive).

        Notes:
        - The breakdown granularity is one day.
        - Only days with non-zero consumption are included in the response.
        """
        response = await self.httpx_client.get(
            f"/organizations/{organization_id}/breakdown_expenses",
            params={
                "start_date": start_period,
                "end_date": end_period,
                "breakdown_by": "cloud_account_id",
            },
        )
        response.raise_for_status()
        return response

    async def fetch_datasource_by_id(self, datasource_id: UUID | str) -> httpx.Response:
        response = await self.httpx_client.get(
            f"/cloud_accounts/{datasource_id}",
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

    async def fetch_user_by_id(self, user_id: UUID | str) -> httpx.Response:
        response = await self.httpx_client.get(
            f"/employees/{user_id}?roles=true",
        )
        response.raise_for_status()
        return response

    async def update_organization_name(
        self,
        id: str,
        name: str,
    ) -> httpx.Response:
        response = await self.httpx_client.patch(
            f"/organizations/{id}",
            json={"name": name},
        )
        response.raise_for_status()
        return response

    async def suspend_organization(
        self,
        organization_id: str,
    ) -> httpx.Response:
        response = await self.httpx_client.patch(
            f"/organizations/{organization_id}",
            json={"disabled": True},
        )
        response.raise_for_status()
        return response


class OptscaleAuthClient(BaseAPIClient):
    @property
    def base_url(self):
        return self.settings.optscale_auth_api_base_url

    @property
    def auth(self):
        return OptscaleClusterSecretAuth(self.settings)

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
