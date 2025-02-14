from fastapi_pagination import create_page, resolve_params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.limit_offset import LimitOffsetParams
from sqlalchemy import ColumnExpressionArgument
from sqlalchemy.orm.interfaces import ORMOption

from app.db.handlers import ModelHandler
from app.db.models import Base
from app.schemas import BaseSchema, from_orm


async def paginate[M: Base, S: BaseSchema](
    handler: ModelHandler[M],
    schema_cls: type[S],
    *,
    extra_conditions: list[ColumnExpressionArgument] | None = None,
) -> AbstractPage[S]:
    params: LimitOffsetParams = resolve_params()
    extra_conditions = extra_conditions or []

    total = await handler.count(*extra_conditions)
    items = await handler.fetch_page(
        limit=params.limit, offset=params.offset, extra_conditions=extra_conditions
    )

    return create_page(
        [from_orm(schema_cls, item) for item in items],
        params=params,
        total=total,
    )
