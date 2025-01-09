from contextvars import ContextVar
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.db import DBSession
from app.db.models import System

current_system = ContextVar[System]("current_system")

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
    db_session: DBSession, credentials: Annotated[JWTCredentials, Depends(JWTBearer())]
):
    from app.db.handlers import DatabaseError, SystemHandler

    system_handler = SystemHandler(db_session)
    try:
        system_id = credentials.claim["sub"]
        system = await system_handler.get(system_id)
        jwt.decode(
            credentials.credentials,
            system.jwt_secret,
            options={"require": ["exp", "nbf", "iat", "sub"]},
            algorithms=[JWT_ALGORITHM],
        )
    except (jwt.InvalidTokenError, DatabaseError) as e:
        raise UNAUTHORIZED_EXCEPTION from e

    reset_token = current_system.set(system)

    try:
        yield system
    finally:
        current_system.reset(reset_token)


CurrentSystem = Annotated[System, Depends(get_current_system)]
