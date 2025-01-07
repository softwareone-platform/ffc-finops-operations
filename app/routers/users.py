import secrets

import svcs
from fastapi import APIRouter, HTTPException, status

from app.api_clients import APIModifierClient, OptscaleAuthClient, OptscaleClient, UserDoesNotExist
from app.auth import CurrentSystem
from app.schemas import UserCreate, UserRead
from app.utils import wrap_http_error_in_502

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    system: CurrentSystem,
    services: svcs.fastapi.DepContainer,
):
    api_modifier_client = await services.aget(APIModifierClient)
    async with wrap_http_error_in_502("Error creating user in FinOps for Cloud"):
        create_user_response = await api_modifier_client.create_user(
            email=data.email,
            display_name=data.display_name,
            password=secrets.token_urlsafe(128),
        )

    optscale_client = await services.aget(OptscaleClient)
    async with wrap_http_error_in_502("Error resetting the password for user in FinOps for Cloud"):
        await optscale_client.reset_password(data.email)

        return UserRead(**create_user_response.json())


@router.get("/{email}", response_model=UserRead)
async def get_user_by_email(
    email: str,
    system: CurrentSystem,
    services: svcs.fastapi.DepContainer,
):
    optscale_auth_client = await services.aget(OptscaleAuthClient)
    async with wrap_http_error_in_502("Error checking user existence in FinOps for Cloud"):
        try:
            response = await optscale_auth_client.get_existing_user_info(email)
        except UserDoesNotExist:
            raise HTTPException(
                status_code=404, detail=f"A user with the email `{email}` wasn't found."
            )
        else:
            return UserRead(**response.json()["user_info"])
