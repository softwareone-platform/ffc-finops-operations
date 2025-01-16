import abc
import inspect
import json
import logging
from collections.abc import Generator
from types import TracebackType
from typing import ClassVar, Self

import httpx

from app import settings
from app.utils import get_api_modifier_jwt_token

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    client_name: ClassVar[str]

    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.client_name = cls.__module__.split(".")[-1]

    def __init__(self, message: str):
        self.message = message

        super().__init__(f"{self.client_name} API client error: {message}")


class APIModifierJWTTokenAuth(httpx.Auth):
    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        # NOTE: Needs to be re-generated for each request as it exipres after a certain time
        jwt_token = get_api_modifier_jwt_token()

        request.headers["Authorization"] = f"Bearer {jwt_token}"

        yield request


class OptscaleClusterSecretAuth(httpx.Auth):
    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Secret"] = settings.opt_cluster_secret

        yield request


HEADERS_TO_REDACT_IN_LOGS = {"authorization", "secret"}


class BaseAPIClient(abc.ABC):
    base_url: ClassVar[str]
    default_auth: ClassVar[httpx.Auth | None] = None

    _clients_by_name: ClassVar[dict[str, type[Self]]] = {}

    def __init_subclass__(cls):
        super().__init_subclass__()

        if inspect.isabstract(cls):  # pragma: no cover
            return

        client_name = cls.__module__.split(".")[-1]
        cls._clients_by_name[client_name] = cls

    @classmethod
    def get_clients_by_name(cls) -> dict[str, type[Self]]:
        return cls._clients_by_name

    def __init__(self):
        self.httpx_client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.default_auth,
            event_hooks={"request": [self._log_request], "response": [self._log_response]},
        )

    async def __aenter__(self) -> Self:
        await self.httpx_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        return await self.httpx_client.__aexit__(exc_type, exc_val, exc_tb)

    # ===============
    # Logging Methods
    # ===============

    def _get_headers_to_log(self, headers: httpx.Headers) -> dict[str, str]:
        return {
            key: (value if key.lower() not in HEADERS_TO_REDACT_IN_LOGS else "REDACTED")
            for key, value in headers.items()
        }

    async def _log_request(self, request: httpx.Request) -> None:
        structured_log_data = {
            "method": request.method,
            "host": request.url.host,
            "port": request.url.port,
            "path": request.url.raw_path,
            "headers": self._get_headers_to_log(request.headers),
            "params": request.url.params,
        }

        try:
            structured_log_data["json"] = json.loads(request.content)
        except json.JSONDecodeError:
            structured_log_data["content"] = request.content

        logger.info(
            "Request event hook: %s %s - Waiting for response",
            request.method,
            request.url,
            extra=structured_log_data,
        )

    async def _log_response(self, response: httpx.Response) -> None:
        request = response.request

        structured_log_data = {
            "method": request.method,
            "host": request.url.host,
            "port": request.url.port,
            "path": request.url.raw_path,
            "headers": self._get_headers_to_log(response.headers),
            "status_code": response.status_code,
            "is_error": response.is_error,
        }

        await response.aread()
        try:
            structured_log_data["json"] = response.json()
        except json.JSONDecodeError:
            structured_log_data["content"] = response.content

        logger.info(
            "Response event hook: %s %s - Status %s",
            request.method,
            request.url,
            response.status_code,
            extra=structured_log_data,
        )
