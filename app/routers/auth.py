from fastapi import APIRouter, status

from app.schemas import Login, LoginRead, RefreshAccessToken

router = APIRouter()


# No auth


@router.post("/tokens", response_model=LoginRead)
async def get_access_token(data: Login | RefreshAccessToken):
    pass


@router.post("/password-recovery-requests/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def start_reset_password_flow(email: str):
    pass
