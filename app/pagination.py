from fastapi_pagination import create_page, resolve_params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.limit_offset import LimitOffsetParams

from app.db.handlers import ModelHandler
from app.db.models import Base
from app.schemas import BaseSchema, from_orm


async def paginate[M: Base, S: BaseSchema](
    handler: ModelHandler[M], schema_cls: type[S]
) -> AbstractPage[S]:
    params: LimitOffsetParams = resolve_params()
    total = await handler.count()
    items = await handler.fetch_page(limit=params.limit, offset=params.offset)
    return create_page(
        [from_orm(schema_cls, item) for item in items],
        params=params,
        total=total,
    )
