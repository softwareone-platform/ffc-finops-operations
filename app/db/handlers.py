from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnExpressionArgument, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.interfaces import ORMOption

from app.auth.context import auth_context
from app.db.db import AsyncTxSession
from app.db.models import (
    Account,
    AccountUser,
    AuditableMixin,
    Entitlement,
    Organization,
    System,
    User,
)
from app.db.models import Base as BaseModel
from app.enums import (
    AccountStatus,
    AccountUserStatus,
    EntitlementStatus,
    OrganizationStatus,
    SystemStatus,
    UserStatus,
)


class DatabaseError(Exception):
    pass


class NotFoundError(DatabaseError):
    pass


class ConstraintViolationError(DatabaseError):
    pass


class ModelHandler[M: BaseModel]:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.commit = not isinstance(self.session, AsyncTxSession)
        self.default_options: list[ORMOption] = []
        self.default_extra_conditions: list[ColumnExpressionArgument] | None = None

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
        if isinstance(obj, AuditableMixin):  # pragma: no branch
            if obj.created_by is None:
                with suppress(LookupError):
                    obj.created_by = auth_context.get().get_actor()

            if obj.updated_by is None:
                with suppress(LookupError):
                    obj.updated_by = auth_context.get().get_actor()

        try:
            self.session.add(obj)
            await self._save_changes(obj)
        except IntegrityError as e:
            raise ConstraintViolationError(
                f"Failed to create {self.model_cls.__name__}: {e}"
            ) from e

        return obj

    async def get(
        self, id: str, extra_conditions: list[ColumnExpressionArgument] | None = None
    ) -> M:
        extra_conditions = extra_conditions or self.default_extra_conditions
        try:
            query = select(self.model_cls).where(
                self.model_cls.id == id,
            )
            if extra_conditions:
                query = query.where(*extra_conditions)
            if self.default_options:
                query = query.options(*self.default_options)
            result = await self.session.execute(query)
            instance = result.scalar_one_or_none()
            if instance is None:
                raise NotFoundError(f"{self.model_cls.__name__} with ID `{str(id)}` wasn't found")
            return instance
        except DBAPIError as e:
            raise DatabaseError(
                f"Failed to get {self.model_cls.__name__} with ID `{str(id)}`: {e}"
            ) from e

    async def get_or_create(
        self, *, defaults: dict[str, Any] | None = None, **filters: Any
    ) -> tuple[M, bool]:
        defaults = defaults or {}
        query = select(self.model_cls).where(
            *(getattr(self.model_cls, key) == value for key, value in filters.items())
        )
        if self.default_options:
            query = query.options(*self.default_options)
        result = await self.session.execute(query)
        obj = result.scalars().first()

        if obj:
            return obj, False

        params = filters
        params.update(defaults)

        obj = await self.create(self.model_cls(**params))
        return obj, True

    async def update(self, id: str, data: dict[str, Any]) -> M:
        obj = await self.get(id)

        for key, value in data.items():
            setattr(obj, key, value)

        if isinstance(obj, AuditableMixin) and "updated_by" not in data:  # pragma: no branch
            with suppress(LookupError):
                obj.updated_by = auth_context.get().get_actor()

        await self._save_changes(obj)
        return obj

    async def fetch_page(
        self,
        limit: int = 50,
        offset: int = 0,
        extra_conditions: list[ColumnExpressionArgument] | None = None,
    ) -> Sequence[M]:
        extra_conditions = extra_conditions or self.default_extra_conditions
        query = select(self.model_cls).offset(offset).limit(limit).order_by("id")
        if extra_conditions:
            query = query.where(*extra_conditions)
        if self.default_options:
            query = query.options(*self.default_options)

        results = await self.session.execute(query)
        return results.scalars().all()

    async def count(self, extra_conditions: list[ColumnExpressionArgument] | None = None) -> int:
        extra_conditions = extra_conditions or self.default_extra_conditions
        query = select(func.count(self.model_cls.id))
        if extra_conditions:
            query = query.where(*extra_conditions)
        result = await self.session.execute(query)
        return result.scalars().one()

    async def _save_changes(self, obj: M):
        if self.commit:
            await self.session.commit()
        else:
            await self.session.flush()
        await self.session.refresh(obj)


class EntitlementHandler(ModelHandler[Entitlement]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [joinedload(Entitlement.owner)]
        self.default_extra_conditions = [Entitlement.status != EntitlementStatus.DELETED]

    async def terminate(self, entitlement: Entitlement) -> Entitlement:
        return await self.update(
            entitlement.id,
            {
                "status": EntitlementStatus.TERMINATED,
                "terminated_at": datetime.now(UTC),
                "terminated_by": auth_context.get().get_actor(),
            },
        )


class OrganizationHandler(ModelHandler[Organization]):
    def __init__(self, session):
        super().__init__(session)
        self.default_extra_conditions = [Organization.status != OrganizationStatus.DELETED]


class SystemHandler(ModelHandler[System]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [joinedload(System.owner)]
        self.default_extra_conditions = [System.status != SystemStatus.DELETED]


class AccountHandler(ModelHandler[Account]):
    def __init__(self, session):
        super().__init__(session)
        self.default_extra_conditions = [Account.status != AccountStatus.DELETED]


class UserHandler(ModelHandler[User]):
    def __init__(self, session):
        super().__init__(session)
        self.default_extra_conditions = [User.status != UserStatus.DELETED]


class AccountUserHandler(ModelHandler[AccountUser]):
    def __init__(self, session):
        super().__init__(session)
        self.default_extra_conditions = [AccountUser.status != AccountUserStatus.DELETED]

    async def get_account_user(
        self,
        account_id: str,
        user_id: str,
        extra_conditions: list[ColumnExpressionArgument] | None = None,
    ) -> AccountUser | None:
        extra_conditions = extra_conditions or self.default_extra_conditions
        query = select(self.model_cls).where(
            self.model_cls.account_id == account_id,
            self.model_cls.user_id == user_id,
        )
        if extra_conditions:
            query = query.where(*extra_conditions)
        if self.default_options:
            query = query.options(*self.default_options)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
