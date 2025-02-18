from fastapi import APIRouter, status
from fastapi_pagination.limit_offset import LimitOffsetPage

from app.schemas.charges import ChargesFileRead

router = APIRouter()


@router.get(
    "",
    response_model=LimitOffsetPage[ChargesFileRead],
)
async def get_charges_files():
    # pending implementation
    pass  # pragma: no cover


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
