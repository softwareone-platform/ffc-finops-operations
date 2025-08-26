import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, status
from sqlalchemy import func

from app.auth.login import get_tokens_from_credentials, get_tokens_from_refresh
from app.db.models import User
from app.dependencies.core import AppSettings
from app.dependencies.db import DBSession, UserRepository
from app.enums import UserStatus
from app.schemas.auth import Login, LoginRead, RefreshAccessToken

router = APIRouter()


@router.post(
    "/tokens",
    response_model=LoginRead,
    responses={
        200: {
            "description": "Access Token Response",
            "content": {
                "application/json": {
                    "example": {
                        "user": {
                            "name": "John Doe",
                            "email": "john.doe@example.com",
                            "id": "FUSR-1234-5678",
                        },
                        "account": {
                            "id": "FACC-1029-2028",
                            "name": "Acme Inc",
                            "type": "operations",
                        },
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...",
                        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...",
                    }
                }
            },
        },
    },
)
async def get_access_token(
    settings: AppSettings,
    db_session: DBSession,
    data: Annotated[
        Login | RefreshAccessToken,
        Body(
            openapi_examples={
                "login_last_used_account": {
                    "summary": "Get Token for Last Used Account.",
                    "description": (
                        "Get an access token for the last used account using the user credentials."
                    ),
                    "value": {
                        "email": "john.doe@example.com",
                        "password": "MyStr@ngL@ngPwd1",
                    },
                },
                "login_specific_account": {
                    "summary": "Get Token for Specific Account.",
                    "description": (
                        "Get an access token for a specific account using the user credentials."
                    ),
                    "value": {
                        "email": "john.doe@example.com",
                        "password": "MyStr@ngL@ngPwd1",
                        "account": {"id": "FACC-1029-2028"},
                    },
                },
                "refresh_token": {
                    "summary": "Get Access Token with Refresh Token.",
                    "description": ("Get a fresh access token using the refresh token."),
                    "value": {
                        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...",
                        "account": {"id": "FACC-1029-2028"},
                    },
                },
            }
        ),
    ],
):
    """
    Get an access token for consuming the Operations API.
    """
    if isinstance(data, Login):
        return await get_tokens_from_credentials(settings, db_session, data)
    return await get_tokens_from_refresh(settings, db_session, data)


@router.post("/password-recovery-requests/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def start_reset_password_flow(
    settings: AppSettings,
    email: str,
    user_repo: UserRepository,
):
    user = await user_repo.first(
        where_clauses=[func.lower(User.email) == email.lower(), User.status == UserStatus.ACTIVE]
    )

    if user and (
        not user.pwd_reset_token_expires_at or user.pwd_reset_token_expires_at < datetime.now(UTC)
    ):
        user.pwd_reset_token = secrets.token_urlsafe(settings.pwd_reset_token_length)
        user.pwd_reset_token_expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.pwd_reset_token_length_expires_minutes,
        )
        await user_repo.update(user)
