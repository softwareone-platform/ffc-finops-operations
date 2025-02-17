from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends

from app.api_clients.api_modifier import APIModifierClient as _APIModifierClient
from app.api_clients.api_modifier import APIModifierClientError
from app.api_clients.base import BaseAPIClient
from app.api_clients.optscale import OptscaleAuthClient as _OptscaleAuthClient
from app.api_clients.optscale import OptscaleAuthClientError, OptscaleClientError, UserDoesNotExist
from app.api_clients.optscale import OptscaleClient as _OptscaleClient
from app.conf import AppSettings


class APIClientFactory[T: BaseAPIClient]:
    def __init__(self, client_cls: type[T]):
        self.client_cls = client_cls

    async def __call__(self, settings: AppSettings) -> AsyncGenerator[T]:
        client = self.client_cls(settings)
        async with client:
            yield client


APIModifierClient = Annotated[_APIModifierClient, Depends(APIClientFactory(_APIModifierClient))]
OptscaleClient = Annotated[_OptscaleClient, Depends(APIClientFactory(_OptscaleClient))]
OptscaleAuthClient = Annotated[_OptscaleAuthClient, Depends(APIClientFactory(_OptscaleAuthClient))]

__all__ = [
    "APIModifierClient",
    "APIModifierClientError",
    "OptscaleClient",
    "OptscaleAuthClient",
    "OptscaleAuthClientError",
    "OptscaleClientError",
    "UserDoesNotExist",
]
