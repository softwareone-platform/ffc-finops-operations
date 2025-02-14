from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from app.api_clients.base import (
    APIClientError,
    BaseAPIClient,
)
from app.conf import Settings

API_MODIFIER_JWT_ALGORITHM = "HS256"
API_MODIFIER_JWT_ISSUER = "SWO"
API_MODIFIER_JWT_AUDIENCE = "modifier"
API_MODIFIER_JWT_EXPIRE_AFTER_SECONDS = 300


class APIModifierClientError(APIClientError):
    pass


class APIModifierJWTTokenAuth(httpx.Auth):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        # NOTE: Needs to be re-generated for each request as it exipres after a certain time
        jwt_token = self.get_api_modifier_jwt_token()

        request.headers["Authorization"] = f"Bearer {jwt_token}"

        yield request

    def get_api_modifier_jwt_token(self) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iss": API_MODIFIER_JWT_ISSUER,
                "aud": API_MODIFIER_JWT_AUDIENCE,
                "iat": int(now.timestamp()),
                "nbf": int(now.timestamp()),
                "exp": int(
                    (now + timedelta(seconds=API_MODIFIER_JWT_EXPIRE_AFTER_SECONDS)).timestamp()
                ),
            },
            self.settings.api_modifier_jwt_secret,
            algorithm=API_MODIFIER_JWT_ALGORITHM,
        )


class APIModifierClient(BaseAPIClient):
    @property
    def base_url(self):
        return self.settings.api_modifier_base_url

    @property
    def auth(self):
        return APIModifierJWTTokenAuth(self.settings)

    async def create_user(self, email: str, display_name: str, password: str) -> httpx.Response:
        response = await self.httpx_client.post(
            "/users",
            json={
                "email": email,
                "display_name": display_name,
                "password": password,
            },
        )

        response.raise_for_status()
        return response

    async def create_organization(
        self,
        org_name: str,
        user_id: str,
        currency: str,
    ) -> httpx.Response:
        response = await self.httpx_client.post(
            "/organizations",
            json={
                "org_name": org_name,
                "user_id": user_id,
                "currency": currency,
            },
        )
        response.raise_for_status()
        return response
