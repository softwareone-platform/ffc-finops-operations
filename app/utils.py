import contextlib
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from fastapi import HTTPException, status

from app import settings
from app.constants import (
    API_MODIFIER_JWT_ALGORITHM,
    API_MODIFIER_JWT_AUDIENCE,
    API_MODIFIER_JWT_EXPIRE_AFTER_SECONDS,
    API_MODIFIER_JWT_ISSUER,
)


def get_api_modifier_jwt_token() -> str:
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
        settings.api_modifier_jwt_secret,
        algorithm=API_MODIFIER_JWT_ALGORITHM,
    )


@contextlib.asynccontextmanager
async def wrap_http_error_in_502(base_msg: str = "Error in FinOps for Cloud"):
    try:
        yield
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{base_msg}: {e.response.status_code} - {e.response.text}.",
        ) from e
