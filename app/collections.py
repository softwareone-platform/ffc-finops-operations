from collections.abc import Sequence
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from fastapi_pagination.ext.sqlmodel import paginate
from fastapi_pagination.limit_offset import LimitOffsetPage, LimitOffsetParams
from sqlmodel import SQLModel, col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Entitlement, EntitlementCreate, EntitlementUpdate, UUIDModel


class BaseCollection[ModelT: UUIDModel, ModelCreateT: SQLModel, ModelUpdateT: SQLModel]:
    def __init__(self, session: AsyncSession):
        self.session = session

    @classmethod
    def _get_generic_cls_args(cls):
        return next(
            base_cls.__args__
            for base_cls in cls.__orig_bases__
            if base_cls.__origin__ is BaseCollection
        )

    @property
    def model_cls(self) -> type[ModelT]:
        return self._get_generic_cls_args()[0]

    @property
    def model_create_cls(self) -> type[ModelCreateT]:  # pragma: no cover
        return self._get_generic_cls_args()[1]

    @property
    def model_update_cls(self) -> type[ModelCreateT]:  # pragma: no cover
        return self._get_generic_cls_args()[2]

    async def create(self, data: ModelCreateT) -> ModelT:
        obj = self.model_cls(**data.model_dump())
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)

        return obj

    async def get(self, id: str | UUID) -> ModelT:
        obj = await self.session.get(self.model_cls, id)

        if obj is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"{self.model_cls.__name__} with ID {str(id)} wasn't found",
            )

        return obj

    async def fetch_all(self) -> Sequence[ModelT]:
        results = await self.session.exec(select(self.model_cls))
        return results.all()

    async def fetch_page(
        self, pagination_params: LimitOffsetParams | None = None
    ) -> LimitOffsetPage[ModelT]:
        return await paginate(self.session, self.model_cls, pagination_params)

    # TODO: Remove the 'no cover' comment once we have collections which make use of this
    async def update(self, id: str | UUID, data: ModelUpdateT) -> ModelT:  # pragma: no cover
        statement = select(self.model_cls).where(self.model_cls.id == id)
        results = await self.session.exec(statement)

        obj: ModelT | None = results.first()

        if obj is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"{self.model_cls.__name__} with ID {str(id)} wasn't found",
            )

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)

        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)

        return obj

    # TODO: Remove the 'no cover' comment once we have collections which make use of this
    async def delete(self, id: str | UUID) -> bool:  # pragma: no cover
        statement = delete(self.model_cls).where(col(self.model_cls.id) == id)

        await self.session.execute(statement=statement)
        await self.session.commit()

        return True


class EntitlementCollection(BaseCollection[Entitlement, EntitlementCreate, EntitlementUpdate]):
    pass
