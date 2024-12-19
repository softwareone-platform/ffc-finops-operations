from typing import TypeVar, get_args
from uuid import UUID

from sqlalchemy.exc import NoResultFound
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Entitlement, Organization

T = TypeVar("T", bound=SQLModel)


class NotFoundError(Exception):
    pass


class Repository[T]:
    model_cls: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    def __init_subclass__(cls) -> None:
        cls.model_cls = get_args(cls.__orig_bases__[0])[0]

    async def create(self, data: T) -> T:
        obj = self.model_cls(**data.model_dump())
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)

        return obj

    async def get(self, id: str | UUID) -> T | None:
        try:
            return await self.session.get_one(self.model_cls, id)
        except NoResultFound:
            raise NotFoundError(f"{self.model_cls.__name__} with ID {str(id)} wasn't found")

    async def update(self, obj: T, data: T) -> T:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)

        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)

        return obj


class EntitlementRepository(Repository[Entitlement]):
    pass


class OrganizationRepository(Repository[Organization]):
    pass
