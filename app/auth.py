from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.handlers import DatabaseError
from app.db.models import System
from app.repositories import SystemRepository

JWT_ALGORITHM = "HS256"


class JWTCredentials(HTTPAuthorizationCredentials):
    claim: dict[str, Any]


UNAUTHORIZED_EXCEPTION = HTTPException(status_code=401, detail="Unauthorized")


class JWTBearer(HTTPBearer):
    def __init__(self):
        super().__init__(auto_error=False)

    async def __call__(self, request: Request) -> JWTCredentials:
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
                pass

        raise UNAUTHORIZED_EXCEPTION


async def get_current_system(
    system_repo: SystemRepository, credentials: Annotated[JWTCredentials, Depends(JWTBearer())]
):
    try:
        system_id = credentials.claim["sub"]
        system = await system_repo.get(system_id)
        jwt.decode(
            credentials.credentials,
            system.jwt_secret,
            options={"require": ["exp", "nbf", "iat", "sub"]},
            algorithms=[JWT_ALGORITHM],
        )
        return system
    except (jwt.InvalidTokenError, DatabaseError) as e:
        raise UNAUTHORIZED_EXCEPTION from e


CurrentSystem = Annotated[System, Depends(get_current_system)]
