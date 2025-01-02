from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi import Depends

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient, HeaderAuth


class OptscaleAuthClientError(APIClientError):
    client_name = "OptscaleAuth"


class UserDoesNotExist(OptscaleAuthClientError):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"User with email {email} does not exist")


class OptscaleAuthClient(BaseAPIClient):
    base_url = settings.opt_auth_base_url
    auth = HeaderAuth("Secret", settings.opt_cluster_secret)

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


async def get_optscale_auth_client() -> AsyncGenerator[OptscaleAuthClient]:
    async with OptscaleAuthClient() as client:
        yield client


OptscaleAuth = Annotated[OptscaleAuthClient, Depends(get_optscale_auth_client)]
