from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import ColumnExpressionArgument, Select

from app.db.models import ChargesFile
from app.dependencies.auth import CurrentAuthContext
from app.dependencies.db import ChargesFileRepository
from app.enums import AccountType, ChargesFileStatus
from app.pagination import LimitOffsetPage, paginate
from app.rql import ChargesFileRules, RQLQuery
from app.schemas.charges import ChargesFileRead


def common_extra_conditions(auth_ctx: CurrentAuthContext) -> list[ColumnExpressionArgument]:
    conditions: list[ColumnExpressionArgument] = []

    if auth_ctx.account.type == AccountType.AFFILIATE:  # type: ignore
        conditions.append(ChargesFile.owner == auth_ctx.account)  # type: ignore
        conditions.append(ChargesFile.status != ChargesFileStatus.DELETED)

    return conditions


CommonConditions = Annotated[list[ColumnExpressionArgument], Depends(common_extra_conditions)]

router = APIRouter()


@router.get(
    "",
    response_model=LimitOffsetPage[ChargesFileRead],
)
async def get_charges_files(
    charges_file_repo: ChargesFileRepository,
    extra_conditions: CommonConditions,
    base_query: Select = Depends(RQLQuery(ChargesFileRules())),
):
    return await paginate(
        charges_file_repo,
        ChargesFileRead,
        where_clauses=extra_conditions,
        base_query=base_query,
    )


@router.get(
    "/{id}",
    response_model=ChargesFileRead,
)
async def get_charges_file_by_id(id: str):
    # pending implementation
    pass  # pragma: no cover


@router.get(
    "/{id}/download",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def download_charges_file(id: str):
    # pending implementation
    # call the download
    # return the full URL witht the SAS token
    pass  # pragma: no cover
