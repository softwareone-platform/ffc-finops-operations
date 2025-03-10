from __future__ import annotations

from collections.abc import Sequence

from fastapi import Query
from fastapi_pagination import create_page, resolve_params
from fastapi_pagination.bases import AbstractPage, AbstractParams, RawParams
from fastapi_pagination.limit_offset import LimitOffsetPage as _LimitOffsetPage
from fastapi_pagination.types import GreaterEqualZero
from pydantic import BaseModel
from sqlalchemy import ColumnExpressionArgument, Exists
from sqlalchemy.orm.interfaces import ORMOption

from app.db.handlers import ModelHandler
from app.db.models import Base
from app.schemas.core import BaseSchema, convert_model_to_schema


class LimitOffsetParams(BaseModel, AbstractParams):
    limit: int = Query(50, ge=0, le=1000, description="Page size limit")
    offset: int = Query(0, ge=0, description="Page offset")

    def to_raw_params(self) -> RawParams:
        return RawParams(
            limit=self.limit,
            offset=self.offset,
        )


class LimitOffsetPage[S: BaseSchema](_LimitOffsetPage[S]):
    limit: GreaterEqualZero | None

    __params_type__ = LimitOffsetParams  # type: ignore


async def paginate[M: Base, S: BaseSchema](
    handler: ModelHandler[M],
    schema_cls: type[S],
    *,
    extra_conditions: Sequence[ColumnExpressionArgument | Exists] | None = None,
    page_options: list[ORMOption] | None = None,
) -> AbstractPage[S]:
    """
    This function queries a database model (M) using a ModelHandler.
    It applies optional filtering (extra_conditions) and query options (options).
    It then serializes the results into a schema (S) and returns
    a paginated response in the form of AbstractPage[S].
    """
    params: LimitOffsetParams = resolve_params()
    total = await handler.count(*(extra_conditions or []))
    items: Sequence[M] = []
    if params.limit > 0:
        items = await handler.fetch_page(
            limit=params.limit,
            offset=params.offset,
            extra_conditions=extra_conditions,
            options=page_options,
        )

    return create_page(
        [convert_model_to_schema(schema_cls, item) for item in items],
        params=params,
        total=total,
    )
