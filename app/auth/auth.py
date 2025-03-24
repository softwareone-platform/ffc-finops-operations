from typing import Any

import jwt
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.constants import JWT_ALGORITHM, UNAUTHORIZED_EXCEPTION


class JWTCredentials(HTTPAuthorizationCredentials):
    claim: dict[str, Any]


class JWTBearer(HTTPBearer):
    def __init__(self):
        super().__init__(auto_error=False)

    async def __call__(self, request: Request) -> JWTCredentials | None:
        credentials = await super().__call__(request)
        if credentials:
            try:
                return JWTCredentials(
                    scheme=credentials.scheme,
                    credentials=credentials.credentials,
                    claim=jwt.decode(
                        credentials.credentials,
                        "",
                        options={"verify_signature": False},
                        algorithms=[JWT_ALGORITHM],
                    ),
                )
            except jwt.InvalidTokenError:
                raise UNAUTHORIZED_EXCEPTION
