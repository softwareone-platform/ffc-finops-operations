from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_system
from app.db.models import AuditableMixin, Entitlement, Organization, System
from app.db.models import Base as BaseModel
from app.enums import EntitlementStatus


class DatabaseError(Exception):
    pass


class NotFoundError(DatabaseError):
    pass


class ConstraintViolationError(DatabaseError):
    pass


class ModelHandler[M: BaseModel]:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @classmethod
    def _get_generic_cls_args(cls):
        return next(
            base_cls.__args__
            for base_cls in cls.__orig_bases__
            if base_cls.__origin__ is ModelHandler
        )

    @property
    def model_cls(self) -> type[M]:
        return self._get_generic_cls_args()[0]

    async def create(self, obj: M) -> M:
        if isinstance(obj, AuditableMixin):
            if obj.created_by is None:
                with suppress(LookupError):
                    obj.created_by = current_system.get()

            if obj.updated_by is None:
                with suppress(LookupError):
                    obj.updated_by = current_system.get()

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
        try:
            result = await self.session.get(self.model_cls, id)
            if result is None:
                raise NotFoundError(f"{self.model_cls.__name__} with ID `{str(id)}` wasn't found")
            return result
        except DBAPIError as e:
            raise DatabaseError(
                f"Failed to get {self.model_cls.__name__} with ID `{str(id)}`: {e}"
            ) from e

    async def get_or_create(
        self, *, defaults: dict[str, Any] | None = None, **filters: Any
    ) -> tuple[M, bool]:
        defaults = defaults or {}
        stmt = select(self.model_cls).where(
            *(getattr(self.model_cls, key) == value for key, value in filters.items())
        )
        result = await self.session.execute(stmt)
        obj = result.scalars().first()

        if obj:
            return obj, False

        params = filters
        params.update(defaults)

        obj = await self.create(self.model_cls(**params))
        return obj, True

    async def update(self, id: str | UUID, data: dict[str, Any]) -> M:
        # First fetch the object to ensure polymorphic loading
        obj = await self.get(id)
        # Update attributes
        for key, value in data.items():
            setattr(obj, key, value)

        if isinstance(obj, AuditableMixin) and "updated_by" not in data:
            with suppress(LookupError):
                obj.updated_by = current_system.get()

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
    async def terminate(self, entitlement: Entitlement) -> Entitlement:
        entitlement.status = EntitlementStatus.TERMINATED
        entitlement.terminated_by = current_system.get()
        entitlement.updated_by = current_system.get()
        entitlement.terminated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(entitlement)

        return entitlement


class OrganizationHandler(ModelHandler[Organization]):
    pass


class SystemHandler(ModelHandler[System]):
    pass
