import abc
import inspect
import json
import logging
from collections.abc import Generator
from types import TracebackType
from typing import ClassVar, Self

import httpx

logger = logging.getLogger(__name__)


class HeaderAuth(httpx.Auth):
    def __init__(self, header_name: str, header_value: str):
        self.header_name = header_name
        self.header_value = header_value

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        if self.header_name not in request.headers:  # pragma: no cover
            request.headers[self.header_name] = self.header_value

        yield request


class BearerAuth(HeaderAuth):
    def __init__(self, token: str):
        super().__init__("Authorization", f"Bearer {token}")


class APIClientError(Exception):
    client_name: ClassVar[str]

    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.client_name = cls.__module__.split(".")[-1]

    def __init__(self, message: str):
        self.message = message

        super().__init__(f"{self.client_name} API client error: {message}")


class BaseAPIClient(abc.ABC):
    base_url: ClassVar[str]
    auth: ClassVar[httpx.Auth | None] = None

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
            base_url=self.get_base_url(),
            auth=self.get_auth(),
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
            key: value
            for key, value in headers.items()
            if not (
                isinstance(self.auth, HeaderAuth) and key.lower() == self.auth.header_name.lower()
            )
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

    # ===========================================
    # Methods for dynamic class fields evaliation
    # ===========================================

    def get_auth(self) -> httpx.Auth | None:
        return self.auth

    def get_base_url(self) -> str:
        return self.base_url
