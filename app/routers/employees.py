import secrets

import svcs
from fastapi import APIRouter, Depends, HTTPException, status

from app.api_clients import APIModifierClient, OptscaleAuthClient, OptscaleClient, UserDoesNotExist
from app.auth.auth import check_operations_account
from app.schemas import EmployeeCreate, EmployeeRead
from app.utils import wrap_http_error_in_502

router = APIRouter(dependencies=[Depends(check_operations_account)])


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    data: EmployeeCreate,
    services: svcs.fastapi.DepContainer,
):
    api_modifier_client = await services.aget(APIModifierClient)
    async with wrap_http_error_in_502("Error creating employee in FinOps for Cloud"):
        create_employee_response = await api_modifier_client.create_user(
            email=data.email,
            display_name=data.display_name,
            password=secrets.token_urlsafe(128),
        )

    optscale_client = await services.aget(OptscaleClient)
    async with wrap_http_error_in_502(
        "Error resetting the password for employee in FinOps for Cloud"
    ):
        await optscale_client.reset_password(data.email)

        return EmployeeRead(**create_employee_response.json())


@router.get("/{email}", response_model=EmployeeRead)
async def get_employee_by_email(
    email: str,
    services: svcs.fastapi.DepContainer,
):
    optscale_auth_client = await services.aget(OptscaleAuthClient)
    async with wrap_http_error_in_502("Error checking employee existence in FinOps for Cloud"):
        try:
            response = await optscale_auth_client.get_existing_user_info(email)
        except UserDoesNotExist:
            raise HTTPException(
                status_code=404, detail=f"An employee with the email `{email}` wasn't found."
            )
        else:
            return EmployeeRead(**response.json()["user_info"])
