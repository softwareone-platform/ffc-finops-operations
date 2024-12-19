from typing import TypeVar, get_args
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from fastapi_pagination.ext.sqlmodel import paginate
from fastapi_pagination.limit_offset import LimitOffsetPage, LimitOffsetParams
from sqlmodel import SQLModel

from app.models import (
    Entitlement,
    EntitlementCreate,
    EntitlementUpdate,
    Organization,
    UUIDModel,
)
from app.repositories import NotFoundError, Repository

ModelT = TypeVar("ModelT", bound=UUIDModel)
ModelCreateT = TypeVar("ModelCreateT", bound=SQLModel)
ModelUpdateT = TypeVar("ModelUpdateT", bound=SQLModel)


class BaseCollection[ModelT]:
    model_cls: type[ModelT]

    def __init__(self, repository: Repository[ModelT]):
        self.repository = repository

    def __init_subclass__(cls) -> None:
        cls.model_cls = get_args(cls.__orig_bases__[0])[0]

    async def get(self, id: str | UUID) -> ModelT:
        try:
            return await self.repository.get(id)
        except NotFoundError as e:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e

    async def fetch_page(
        self, pagination_params: LimitOffsetParams | None = None
    ) -> LimitOffsetPage[ModelT]:
        return await paginate(
            self.repository.session,
            self.repository.model_cls,
            pagination_params,
        )


class CreateMixin[ModelT, ModelCreateT]:
    async def create(self: BaseCollection, data: ModelCreateT) -> ModelT:
        return await self.repository.create(self.model_cls(**data.model_dump()))


class UpdateMixin[ModelT, ModelUpdateT]:
    async def update(self: BaseCollection, id: str | UUID, data: ModelUpdateT) -> ModelT:
        return await self.repository.update(await self.get(id), data)


class EntitlementCollection(
    BaseCollection[Entitlement],
    CreateMixin[Entitlement, EntitlementCreate],
    UpdateMixin[Entitlement, EntitlementUpdate],
):
    pass


class OrganizationCollection(BaseCollection[Organization]):
    pass
