from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.auth.auth import check_operations_account
from app.db.handlers import NotFoundError
from app.db.models import Account
from app.dependencies import AccountId, AccountRepository, CurrentAuthContext, UserId
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


async def update_data_and_format_response(id,account_repo, data):
    """
    It updates the given data to the Account model and return back
    the Pydantic schema

    account_repo: an ORM model instance of AccountRepository
    data: the data to persist
    Return: AccountUpdate Pydantic Model
    """
    print("data:", type(data))
    to_update = data.model_dump(exclude_none=True)
    print("to_update:",to_update)
    if not to_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't update whatever you want.",
        )
    db_account = await account_repo.update(id=id, data=data.model_dump(exclude_none=True))
    print("db_account", db_account.name)
    from_orm_ =  from_orm(AccountRead, db_account)
    print("from orm",from_orm_)
    return from_orm_


async def validate_required_conditions_before_update(account:Account):
    """

    """
    if account.type != AccountType.AFFILIATE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot update an Account of type Operations.",
        )
    if account.status == AccountStatus.DELETED or account.status == AccountStatus.DISABLED:
        raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot update an Account Deleted.",
            )

async def validate_account_type_and_required_conditions(
    account_repo: AccountRepository, data: AccountCreate
):
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
            detail="You cannot create an Account of type Operations.",
        )
    if await account_repo.first(
        Account.external_id == data.external_id, Account.status != AccountStatus.DELETED
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Account with external ID " f"`{data.external_id}` already exists.",
        )


async def fetch_account_or_404(id: AccountId, account_repo: AccountRepository) -> Account:
    try:
        return await account_repo.get(id=id)
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

    There are 3 conditions to check before proceeding with the operation of creation for an account.
    1. The Account type must be OPERATIONS, otherwise a 403 error will be returned
    2. Only Accounts classified as of type “Affiliate” can be created.
    3. The external_id field has to be unique and not in DELETED status.

    The newly created account's status will be assigned as ACTIVE

    Raises:
        - HTTPException with status 403 if the check (1) fails
        - HTTPException with status 400 if the checks (2) or (3) fail.

    """
    await validate_account_type_and_required_conditions(account_repo, data)
    return await persist_data_and_format_response(account_repo, data)


@router.get(
    "/{id}",
    response_model=AccountRead,
    dependencies=[Depends(check_operations_account)],
)
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


@router.put("/{id}", response_model=AccountRead,
            dependencies=[Depends(check_operations_account)],
)
async def update_account(data: AccountUpdate, account_repo: AccountRepository,
                         account: Annotated[Account, Depends(fetch_account_or_404)],
):
    """

    """
    await validate_required_conditions_before_update(account=account)
    return await update_data_and_format_response(account.id, account_repo, data)



@router.get("/{id}/users", response_model=LimitOffsetPage[AccountUserRead])
async def list_account_users(account: Annotated[Account, Depends(fetch_account_or_404)],
                             auth_context: CurrentAuthContext):
    """
    if auth_context.account.type == AFFILIATE && auth_context.account != account
        403
    """
    pass


@router.delete("/{id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_account(account: Annotated[Account, Depends(fetch_account_or_404)],
                                   user_id: UserId):
    """
    if auth_context.account.type == AFFILIATE && auth_context.account != account
        403
    user account != DELETED
    set account user status to DELETE
    set deleted_at to now()
    """
    pass
