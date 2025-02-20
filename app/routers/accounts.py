from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination.limit_offset import LimitOffsetPage
from sqlalchemy import exists

from app.auth.auth import check_operations_account
from app.db.handlers import NotFoundError
from app.db.models import Account, AccountUser, User
from app.dependencies import (
    AccountId,
    AccountRepository,
    AccountUserRepository,
    CurrentAuthContext,
    UserId,
    UserRepository,
)
from app.enums import AccountStatus, AccountType, AccountUserStatus
from app.pagination import paginate
from app.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    UserRead,
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


async def update_data_and_format_response(
    id: str, account_repo: AccountRepository, data: AccountUpdate
):
    """
    It updates the given data to the Account model and return back
    the Pydantic schema

    account_repo: an ORM model instance of AccountRepository
    data: the data to update
    Return: AccountUpdate Pydantic Model
    """
    to_update = data.model_dump(exclude_none=True)
    if not to_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't update whatever you want.",
        )
    db_account = await account_repo.update(id, data=to_update)
    return from_orm(AccountRead, db_account)


def validate_required_conditions_before_update(account: Account):
    """
    This function performs the following required checks before
    proceeding to update an Account:
    1. Only Accounts classified as of type “Affiliate” can be updated.
    2. The account status cannot be DELETED

    A HTTPException with status 400 will be raised if at least one condition is not met.
    """
    if account.type != AccountType.AFFILIATE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot update an Account of type Operations.",
        )
    if account.status == AccountStatus.DELETED:
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


@router.put(
    "/{id}",
    response_model=AccountRead,
    dependencies=[Depends(check_operations_account)],
)
async def update_account(
    data: AccountUpdate,
    account_repo: AccountRepository,
    account: Annotated[Account, Depends(fetch_account_or_404)],
):
    """
    This Endpoint updates an Affiliate Account.

    The following conditions must be verified before proceeding with the operation of updating
    an account.
    1. The Account type must be OPERATIONS, otherwise a 403 error will be returned
    2. The Account status must be Active
    3. Only Accounts classified as of type “Affiliate” can be updated.
    4. Only the name and the external_id of the account can be modified.


    Raises:
        - HTTPException with status 403 if the check (1) fails
        - HTTPException with status 400 if the checks (2), (4) or (3) fail.
    """
    validate_required_conditions_before_update(account=account)
    return await update_data_and_format_response(
        id=account.id, account_repo=account_repo, data=data
    )


@router.get("/{id}/users", response_model=LimitOffsetPage[UserRead])
async def list_account_users(
    account: Annotated[Account, Depends(fetch_account_or_404)],
    auth_context: CurrentAuthContext,
    user_repo: UserRepository,
):
    """
    This Endpoint lists all the users bound to a given account id.
    The output is paginated by default.
    Raises:
        - HTTPException with status 404 if the given account is different from the context account
        - HTTPException 404 if the provided account's id doesn't exist.
    Returns a list of accounts if any.
    """

    if auth_context.account.type == AccountType.AFFILIATE and auth_context.account != account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID `{account.id}` wasn't found.",
        )
    # This runs a JOIN like
    # stmt = (
    #    select(User)
    #    .join(AccountUser, User.id == AccountUser.user_id)
    #    .where(AccountUser.account_id == account.id)
    # )

    return await paginate(
        user_repo,
        UserRead,
        extra_conditions=[
            exists().where(AccountUser.account_id == account.id, User.id == AccountUser.user_id)
        ],
    )


@router.delete("/{id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_account(
    account: Annotated[Account, Depends(fetch_account_or_404)],
    user_id: UserId,
    auth_context: CurrentAuthContext,
    accountuser_repo: AccountUserRepository,
):
    """
    This Endpoint removes a user from the giver account
    Raises:
        - HTTPException with status 404 if the given account is different from the context account
        - HTTPException 400 if the query doesn't return a valid account's user object

    """
    if auth_context.account.type == AccountType.AFFILIATE and auth_context.account != account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID `{account.id}` wasn't found.",
        )
    account_user = await accountuser_repo.get_account_user(
        account_id=account.id,
        user_id=user_id,
        extra_conditions=[AccountUser.status != AccountUserStatus.DELETED],
    )
    if account_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The User `{user_id}` does not belong to the Account with ID `{account.id}`.",
        )
    await accountuser_repo.soft_delete(id_or_obj=account_user)
