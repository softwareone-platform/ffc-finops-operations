from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import ColumnExpressionArgument

from app.db.handlers import NotFoundError
from app.db.models import Account, Entitlement
from app.dependencies import (
    AccountRepository,
    CurrentAuthContext,
    EntitlementId,
    EntitlementRepository,
)
from app.enums import AccountStatus, AccountType, EntitlementStatus
from app.pagination import LimitOffsetPage, paginate
from app.schemas.core import from_orm, to_orm
from app.schemas.entitlements import EntitlementCreate, EntitlementRead, EntitlementRedeem

# ============
# Dependencies
# ============


def common_extra_conditions(auth_ctx: CurrentAuthContext) -> list[ColumnExpressionArgument]:
    conditions: list[ColumnExpressionArgument] = []

    if auth_ctx.account.type == AccountType.AFFILIATE:  # type: ignore
        conditions.append(Entitlement.owner == auth_ctx.account)  # type: ignore

    return conditions


CommonConditions = Annotated[list[ColumnExpressionArgument], Depends(common_extra_conditions)]


async def fetch_entitlement_or_404(
    id: EntitlementId,
    entitlement_repo: EntitlementRepository,
    extra_conditions: CommonConditions,
) -> Entitlement:
    try:
        return await entitlement_repo.get(id=id, extra_conditions=extra_conditions)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ======
# Routes
# ======

router = APIRouter()


@router.get("", response_model=LimitOffsetPage[EntitlementRead])
async def get_entitlements(
    entitlement_repo: EntitlementRepository, extra_conditions: CommonConditions
):
    return await paginate(entitlement_repo, EntitlementRead, extra_conditions=extra_conditions)


@router.post("", response_model=EntitlementRead, status_code=status.HTTP_201_CREATED)
async def create_entitlement(
    data: EntitlementCreate,
    account_repo: AccountRepository,
    entitlement_repo: EntitlementRepository,
    auth_context: CurrentAuthContext,
):
    owner = None
    if auth_context.account.type == AccountType.AFFILIATE:  # type: ignore
        if data.owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Affiliate accounts cannot provide an owner for an Entitlement.",
            )
        owner = auth_context.account  # type: ignore
    else:
        if not data.owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Operations accounts must provide an owner for an Entitlement.",
            )
        try:
            owner = await account_repo.get(
                data.owner.id,
                [Account.status == AccountStatus.ACTIVE, Account.type == AccountType.AFFILIATE],
            )
        except NotFoundError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No Active Affiliate Account has been found with ID {data.owner.id}.",
            )

    entitlement = to_orm(data, Entitlement)
    entitlement.owner = owner
    db_entitlement = await entitlement_repo.create(entitlement)
    return from_orm(EntitlementRead, db_entitlement)


@router.get("/{id}", response_model=EntitlementRead)
async def get_entitlement_by_id(
    entitlement: Annotated[Entitlement, Depends(fetch_entitlement_or_404)],
):
    return from_orm(EntitlementRead, entitlement)


@router.post("/{id}/terminate", response_model=EntitlementRead)
async def terminate_entitlement(
    entitlement: Annotated[Entitlement, Depends(fetch_entitlement_or_404)],
    entitlement_repo: EntitlementRepository,
):
    if entitlement.status == EntitlementStatus.TERMINATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Entitlement is already terminated."
        )

    if entitlement.status != EntitlementStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Only active entitlements can be terminated,"
                f" current status is {entitlement.status.value}."
            ),
        )

    entitlement = await entitlement_repo.terminate(entitlement)

    return from_orm(EntitlementRead, entitlement)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entitlement_by_id(
    entitlement: Annotated[Entitlement, Depends(fetch_entitlement_or_404)],
):
    pass


@router.post("/{id}/redeem", response_model=EntitlementRead)
async def redeem_entitlement(
    entitlement: Annotated[Entitlement, Depends(fetch_entitlement_or_404)],
    redeem_info: EntitlementRedeem,
):
    pass
