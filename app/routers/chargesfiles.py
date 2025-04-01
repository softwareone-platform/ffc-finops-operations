from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import ColumnExpressionArgument, Select

from app.blob_storage import download_charges_file
from app.db.handlers import NotFoundError
from app.db.models import ChargesFile
from app.dependencies.auth import CurrentAuthContext, logger
from app.dependencies.db import ChargesFileRepository
from app.dependencies.path import ChargeFileId
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


async def fetch_charge_file_or_404(
    id: ChargeFileId,
    charge_file_repo: ChargesFileRepository,
    extra_conditions: CommonConditions,
) -> ChargesFile:
    try:
        return await charge_file_repo.get(id=id, extra_conditions=extra_conditions)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


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
async def get_url_to_download_charges_file_by_id(
    charge_file: Annotated[ChargesFile, Depends(fetch_charge_file_or_404)],
):
    filename = charge_file.id
    document_date = charge_file.document_date.isoformat()
    try:
        year, month = map(int, document_date.split("-")[:2])
        response = await download_charges_file(
            filename=filename + ".zip",
            currency=charge_file.currency,
            year=year,
            month=month,
        )
        return response
    except (ValueError, AttributeError, IndexError) as error:  # pragma: no cover
        logger.error("Failed to parse 'document_date' (%s): %s", document_date, error)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
