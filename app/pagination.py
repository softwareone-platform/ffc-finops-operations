from fastapi_pagination import create_page, resolve_params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.limit_offset import LimitOffsetParams

from app.db.handlers import ModelHandler
from app.models import UUIDModel


async def paginate[T: UUIDModel](handler: ModelHandler[T]) -> AbstractPage[T]:
    params: LimitOffsetParams = resolve_params()
    total = await handler.count()
    items = await handler.fetch_page(limit=params.limit, offset=params.offset)
    return create_page(items, params=params, total=total)
