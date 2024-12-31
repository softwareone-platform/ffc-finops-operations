import secrets

import httpx
from fastapi import APIRouter, HTTPException, status

from app import settings
from app.auth import CurrentSystem
from app.schemas import UserCreate, UserRead
from app.utils import get_api_modifier_jwt_token

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, system: CurrentSystem):
    try:
        async with httpx.AsyncClient(base_url=settings.opt_auth_base_url) as client:
            response = await client.get(
                "/user_existence",
                headers={"Secret": settings.opt_cluster_secret},
                params={
                    "email": data.email,
                    "user_info": "true",
                },
            )
            response.raise_for_status()
            exist_user_response = response.json()
            if exist_user_response["exists"]:
                return UserRead(**exist_user_response["user_info"])
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Error checking user existence in FinOps for Cloud: "
                f"{e.response.status_code} - {e.response.text}.",
            ),
        ) from e

    try:
        async with httpx.AsyncClient(base_url=settings.api_modifier_base_url) as client:
            response = await client.post(
                "/admin/users",
                headers={"Authorization": f"Bearer {get_api_modifier_jwt_token()}"},
                json={
                    "email": data.email,
                    "display_name": data.display_name,
                    "password": secrets.token_urlsafe(128),
                },
            )
            response.raise_for_status()
            create_user_response = response.json()

        async with httpx.AsyncClient(base_url=settings.opt_api_base_url) as client:
            response = await client.post(
                "/restore_password",
                json={
                    "email": data.email,
                },
            )
            response.raise_for_status()

        return UserRead(**create_user_response)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Error creating user in FinOps for Cloud: "
                f"{e.response.status_code} - {e.response.text}.",
            ),
        ) from e
