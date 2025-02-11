from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.auth.auth import check_operations_account
from app.db.handlers import NotFoundError
from app.db.models import Account
from app.dependencies import AccountId, AccountRepository
from app.enums import AccountStatus, AccountType
from app.pagination import paginate
from app.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    AccountUserRead,
    from_orm,
    to_orm,
)

router = APIRouter()


async def persist_data_and_format_response(account_repo, data):
    """
    It persists the given data to the Account model and return back
    the Pydantic schema

    account_repo: an ORM model instance of AccountRepository
    data: the data to persist
    Return: AccountRead Pydantic Model
    """
    account = to_orm(data, Account)
    db_account = await account_repo.create(account)
    return from_orm(AccountRead, db_account)


async def validate_account_type_and_required_conditions(account_repo, data):
    """
    This function performs the following required checks before
    proceeding to create an Account:
    1. Only Accounts classified as of type “Affiliate” can be created.
    2. The external_id field has to be unique and not in DELETED status.

    A HTTPException with status 400 will be raised if at least one condition is not met.
    """
    if data.type != AccountType.AFFILIATE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Account with external ID " f"`{data.external_id}` already exists.",
        )
    if await account_repo.first(
        Account.external_id == data.external_id, Account.status != AccountStatus.DELETED
    ):  # noqa: E501
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Account with external ID " f"`{data.external_id}` already exists.",
        )


async def fetch_account_or_404(account_id: AccountId, account_repo: AccountRepository) -> Account:
    try:
        return await account_repo.get(id=account_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_operations_account)],
)
async def create_account(data: AccountCreate, account_repo: AccountRepository):
    """
    This Endpoint creates an Affiliate Account.
    The incoming data looks like
     {
          "name": "Microsoft",
          "external_id": "ACC-9044-8753", # this has to be unique in the DB
          "description": "string",
          "type": "affiliate"
    }
    There are 3 conditions to check before proceeding with the operation of creation for an account.
    1. The Account type must be OPERATIONS, otherwise a 403 error will be returned
    2. Only Accounts classified as of type “Affiliate” can be created.
    3. The external_id field has to be unique and not in DELETED status.

    The newly created account's status will be assigned as ACTIVE

    Raises:
        - HTTPException with status 403 if the check (1) fails
        - HTTPException with status 400 if the checks (2) or (3) fail.
    Return: A dict like the following one
    {
        'id': 'FACC-1369-9180',
        'name': 'Microsoft',
        'external_id': 'ACC-9044-8753',
        'type': 'affiliate',
        'created_at': '2025-02-11T08:26:53.280197Z',
        'updated_at': '2025-02-11T08:26:53.280202Z',
        'deleted_at': None,
        'created_by': {'id': 'FTKN-9219-4796', 'type': 'system', 'name': 'Johnson PLC'},
        'updated_by': {'id': 'FTKN-9219-4796', 'type': 'system', 'name': 'Johnson PLC'},
        'deleted_by': None,
        'entitlements_stats': None,
        'status': 'active'
    }


    """
    await validate_account_type_and_required_conditions(account_repo, data)
    return await persist_data_and_format_response(account_repo, data)


@router.get("/{id}", response_model=AccountRead)
async def get_account_by_id(
    account: Annotated[Account, Depends(fetch_account_or_404)],
):
    return from_orm(AccountRead, account)


@router.get(
    "",
    response_model=LimitOffsetPage[AccountRead],
    dependencies=[Depends(check_operations_account)],
)
async def get_accounts(account_repo: AccountRepository):
    return await paginate(account_repo, AccountRead)


@router.put("/{id}", response_model=AccountRead)
async def update_account(id: str, data: AccountUpdate):
    pass


@router.get("/{id}/users", response_model=LimitOffsetPage[AccountUserRead])
async def list_account_users(id: str):
    pass


@router.delete("/{id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_account(id: str, user_id: str):
    pass
