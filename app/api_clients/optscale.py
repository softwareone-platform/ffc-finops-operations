from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi import Depends

from app import settings
from app.api_clients.base import APIClientError, BaseAPIClient


class OptscaleClientError(APIClientError):
    client_name = "Optscale"


class OptscaleClient(BaseAPIClient):
    base_url = settings.opt_api_base_url

    async def reset_password(self, email: str) -> httpx.Response:
        response = await self.httpx_client.post(
            "/restore_password",
            json={"email": email},
        )

        response.raise_for_status()
        return response


async def get_optscale_client() -> AsyncGenerator[OptscaleClient]:
    async with OptscaleClient() as client:
        yield client


Optscale = Annotated[OptscaleClient, Depends(get_optscale_client)]
