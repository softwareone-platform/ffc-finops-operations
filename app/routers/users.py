import secrets

from fastapi import APIRouter, status

from app.api_clients.api_modifier import APIModifier
from app.api_clients.optscale import Optscale
from app.api_clients.optscale_auth import OptscaleAuth, UserDoesNotExist
from app.auth import CurrentSystem
from app.schemas import UserCreate, UserRead
from app.utils import wrap_http_error_in_502

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    system: CurrentSystem,
    optscale_auth_client: OptscaleAuth,
    api_modifier_client: APIModifier,
    optscale_client: Optscale,
):
    async with wrap_http_error_in_502("Error checking user existence in FinOps for Cloud"):
        try:
            response = await optscale_auth_client.get_existing_user_info(data.email)
        except UserDoesNotExist:
            pass
        else:
            return UserRead(**response.json()["user_info"])

    async with wrap_http_error_in_502("Error creating user in FinOps for Cloud"):
        create_user_response = await api_modifier_client.create_user(
            email=data.email,
            display_name=data.display_name,
            password=secrets.token_urlsafe(128),
        )

        await optscale_client.reset_password(data.email)

        return UserRead(**create_user_response.json())
