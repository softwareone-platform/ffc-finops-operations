import enum

import httpx
import stamina

from app.api_clients.base import APIClientError, BaseAPIClient


class ExchangeRateAPIErrorType(str, enum.Enum):
    # ref: https://www.exchangerate-api.com/docs/standard-requests

    UNSUPPORTED_CODE = "unsupported-code"
    MALFORMED_REQUEST = "malformed-request"
    INVALID_KEY = "invalid-key"
    INACTIVE_ACCOUNT = "inactive-account"
    QUOTA_REACHED = "quota-reached"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class ExchangeRateAPIError(APIClientError):
    # Exchange Rate API can return responses with a "result" field that is not "success"
    # while still being 200 OK responses
    #
    # ref: https://www.exchangerate-api.com/docs/standard-requests
    response: httpx.Response
    response_result: str | None
    error_type: ExchangeRateAPIErrorType

    def __init__(self, response: httpx.Response):
        self.response = response

        try:
            data = response.json()
            self.response_result = data.get("result")
            self.error_type = ExchangeRateAPIErrorType(data.get("error-type", "unknown"))
        except ValueError:  # pragma: no cover
            self.response_result = None
            self.error_type = ExchangeRateAPIErrorType.UNKNOWN

        super().__init__(f"response result is {self.response_result}, code: {self.error_type}")

    def should_retry(self) -> bool:
        return self.error_type == ExchangeRateAPIErrorType.UNKNOWN


class ExchangeRateAPIClient(BaseAPIClient):
    auth = None  # Implemented in base_url

    @property
    def base_url(self):
        return f"{self.settings.exchange_rate_api_base_url}/{self.settings.exchange_rate_api_token}"

    @staticmethod
    def retry_condition(exc: Exception) -> bool:
        # If the error is an HTTP status error, only retry on 5xx errors.
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500

        # "successful" responses (i.e. status_code < 400) can still have errors
        # that we may want to retry on if it makes sense
        if isinstance(exc, ExchangeRateAPIError):
            return exc.should_retry()

        # Retry on all other httpx errors (e.g. timeouts)
        return isinstance(exc, httpx.HTTPError)

    @stamina.retry(on=retry_condition, attempts=3)
    async def get_latest_rates(self, base_currency: str) -> httpx.Response:
        response = await self.httpx_client.get(f"/latest/{base_currency}")
        response.raise_for_status()
        try:
            response_data = response.json()
        except ValueError:  # pragma: no cover
            raise ExchangeRateAPIError(response)

        if response_data.get("result") != "success":
            raise ExchangeRateAPIError(response)

        return response
