from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Entitlement, Organization, UUIDModel


class DBError(Exception):
    pass


class NotFoundError(DBError):
    pass


class ConstraintViolationError(DBError):
    pass


class ModelHandler[T: UUIDModel]:
    def __init__(self, model_cls: type[T], session: AsyncSession) -> None:
        self.model_cls: type[T] = model_cls
        self.session: AsyncSession = session

    async def create(self, data: BaseModel) -> T:
        try:
            obj = self.model_cls(**data.model_dump())
            self.session.add(obj)
            await self.session.commit()
            await self.session.refresh(obj)
        except IntegrityError as e:
            raise ConstraintViolationError(
                f"Failed to create {self.model_cls.__name__}: {e}"
            ) from e

        return obj

    async def get(self, id: str | UUID) -> T:
        try:
            return await self.session.get_one(self.model_cls, id)
        except NoResultFound as e:
            raise NotFoundError(f"{self.model_cls.__name__} with ID {str(id)} wasn't found") from e

    async def update(self, id: str | UUID, data: BaseModel) -> T:  # pragma: no cover
        stmt = (
            update(self.model_cls)
            .where(self.model_cls.id == id)  # type: ignore[attr-defined, arg-type]
            .values(**data.model_dump(exclude_unset=True))
            .returning(self.model_cls)
        )
        try:
            result = await self.session.exec(stmt)  # type: ignore[call-overload]
            obj = result.scalars().one()
            await self.session.commit()
            return obj
        except NoResultFound as e:
            raise NotFoundError(f"{self.model_cls.__name__} with ID {str(id)} wasn't found") from e

    async def fetch_page(self, limit: int = 50, offset: int = 0) -> Sequence[T]:
        results = await self.session.exec(select(self.model_cls).offset(offset).limit(limit))
        return results.all()

    async def count(self) -> int:
        result = await self.session.exec(select(func.count(self.model_cls.id)))  # type: ignore[arg-type]
        return result.one()


class EntitlementHandler(ModelHandler[Entitlement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Entitlement, session)


class OrganizationHandler(ModelHandler[Organization]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Organization, session)
