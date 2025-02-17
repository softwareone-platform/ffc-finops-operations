from fastapi import APIRouter, status

from app.auth.login import get_tokens_from_credentials, get_tokens_from_refresh
from app.conf import AppSettings
from app.dependencies import DBSession
from app.schemas import Login, LoginRead, RefreshAccessToken

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
async def start_reset_password_flow(email: str):
    pass
