from fastapi import APIRouter, Depends, status
from sqlalchemy import Select

from app.dependencies import ChargesFileRepository
from app.pagination import LimitOffsetPage, paginate
from app.rql import ChargesFileRules, RQLQuery
from app.schemas.charges import ChargesFileRead

router = APIRouter()


@router.get(
    "",
    response_model=LimitOffsetPage[ChargesFileRead],
)
async def get_charges_files(
    charges_file_repo: ChargesFileRepository,
    base_query: Select = Depends(RQLQuery(ChargesFileRules())),
):
    return await paginate(
        charges_file_repo,
        ChargesFileRead,
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
    pass  # pragma: no cover
