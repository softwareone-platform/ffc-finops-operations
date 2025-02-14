import json
import logging
from abc import ABC, abstractmethod
from functools import cached_property
from types import TracebackType
from typing import ClassVar, Self

import httpx

from app.conf import Settings

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    client_name: ClassVar[str]

    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.client_name = cls.__module__.split(".")[-1]

    def __init__(self, message: str):
        self.message = message

        super().__init__(f"{self.client_name} API client error: {message}")


HEADERS_TO_REDACT_IN_LOGS = {"authorization", "secret"}


class BaseAPIClient(ABC):
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    @abstractmethod
    def base_url(self):
        raise NotImplementedError("base_url property must be implemented in subclasses")

    @property
    @abstractmethod
    def auth(self):
        raise NotImplementedError("base_url property must be implemented in subclasses")

    @cached_property
    def httpx_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.auth,
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
