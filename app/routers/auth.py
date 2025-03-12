import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status

from app.auth.login import get_tokens_from_credentials, get_tokens_from_refresh
from app.conf import AppSettings
from app.db.models import User
from app.dependencies import DBSession, UserRepository
from app.enums import UserStatus
from app.schemas.auth import Login, LoginRead, RefreshAccessToken

router = APIRouter()


@router.post("/tokens", response_model=LoginRead)
async def get_access_token(
    settings: AppSettings,
    db_session: DBSession,
    data: Login | RefreshAccessToken,
):
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
        where_clauses=[User.email == email, User.status == UserStatus.ACTIVE]
    )

    if user and (
        not user.pwd_reset_token_expires_at or user.pwd_reset_token_expires_at < datetime.now(UTC)
    ):
        user.pwd_reset_token = secrets.token_urlsafe(settings.pwd_reset_token_length)
        user.pwd_reset_token_expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.pwd_reset_token_length_expires_minutes,
        )
        await user_repo.update(user)
