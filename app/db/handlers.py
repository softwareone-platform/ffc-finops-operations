from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base, Entitlement, Organization, System


class NotFoundError(Exception):
    pass


class ConstraintViolationError(Exception):
    pass


class ModelHandler[M: Base]:
    def __init__(self, session: AsyncSession, model_cls: type[M]) -> None:
        self.session = session
        self.model_cls = model_cls

    async def create(self, obj: M) -> M:
        try:
            self.session.add(obj)
            await self.session.commit()
            await self.session.refresh(obj)
        except IntegrityError as e:
            raise ConstraintViolationError(
                f"Failed to create {self.model_cls.__name__}: {e}"
            ) from e

        return obj

    async def get(self, id: UUID | str) -> M:
        result = await self.session.get(self.model_cls, id)
        if result is None:
            raise NotFoundError(f"{self.model_cls.__name__} with ID {str(id)} wasn't found")
        return result

    async def update(self, id: str | UUID, data: dict[str, Any]) -> M:
        # First fetch the object to ensure polymorphic loading
        obj = await self.get(id)
        # Update attributes
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def fetch_page(self, limit: int = 50, offset: int = 0) -> Sequence[M]:
        results = await self.session.execute(select(self.model_cls).offset(offset).limit(limit))
        return results.scalars().all()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(self.model_cls.id)))
        return result.scalars().one()


class EntitlementHandler(ModelHandler[Entitlement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Entitlement)


class OrganizationHandler(ModelHandler[Organization]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Organization)


class SystemHandler(ModelHandler[System]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, System)
