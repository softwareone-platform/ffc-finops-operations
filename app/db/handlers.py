from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import sqlalchemy
from sqlalchemy import ColumnExpressionArgument, Exists, Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.interfaces import ORMOption

from app.auth.context import auth_context
from app.db.models import (
    Account,
    AccountUser,
    AuditableMixin,
    Entitlement,
    Organization,
    System,
    TimestampMixin,
    User,
)
from app.db.models import Base as BaseModel
from app.enums import (
    AccountUserStatus,
    EntitlementStatus,
)


class DatabaseError(Exception):
    pass


class InvalidParameters(Exception):
    pass


class NotFoundError(DatabaseError):
    pass


class CannotDeleteError(DatabaseError):
    pass


class ConstraintViolationError(DatabaseError):
    pass


class NullViolationError(DatabaseError):
    pass


class ModelHandler[M: BaseModel]:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.default_options: list[ORMOption] = []

    @classmethod
    def _get_generic_cls_args(cls):
        """
        Retrieves the generic model class arg dynamically
        """
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

        self.session.add(obj)
        await self._save_changes(obj)

        return obj

    async def get(
        self, id: str, extra_conditions: list[ColumnExpressionArgument] | None = None
    ) -> M:
        query = select(self.model_cls).where(self.model_cls.id == id)
        if extra_conditions:
            query = query.where(*extra_conditions)

        if self.default_options:
            query = query.options(*self.default_options)

        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()

        if instance is None:
            raise NotFoundError(f"{self.model_cls.__name__} with ID `{str(id)}` wasn't found.")

        return instance

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

    async def update(self, id_or_obj: str | M, data: dict[str, Any] | None = None) -> M:
        obj = await self._get_model_obj(id_or_obj)

        if data:
            for key, value in data.items():
                setattr(obj, key, value)

        if (
            isinstance(obj, AuditableMixin) and data and "updated_by" not in data
        ):  # pragma: no branch
            with suppress(LookupError):
                obj.updated_by = auth_context.get().get_actor()

        await self._save_changes(obj)
        return obj

    async def soft_delete(self, id_or_obj: str | M) -> M:
        obj = await self._get_model_obj(id_or_obj)

        model_inspection = sqlalchemy.inspect(obj.__class__)
        status_column = model_inspection.columns.get("status")

        if status_column is None:
            raise CannotDeleteError(f"{self.model_cls.__name__} does not have a status column.")

        if not isinstance(status_column.type, sqlalchemy.Enum):
            raise CannotDeleteError(f"{self.model_cls.__name__} status column is not an Enum.")

        if "deleted" not in status_column.type.enums:
            raise CannotDeleteError(
                f"{self.model_cls.__name__} status column does not have a 'deleted' value."
            )

        if obj.status == "deleted":  # type: ignore[attr-defined]
            raise CannotDeleteError(f"{self.model_cls.__name__} object is already deleted.")

        column_updates = {"status": "deleted"}

        if isinstance(obj, TimestampMixin):
            column_updates["deleted_at"] = datetime.now(UTC)

        if isinstance(obj, AuditableMixin):
            column_updates["updated_by"] = obj.updated_by
            with suppress(LookupError):
                column_updates["deleted_by"] = auth_context.get().get_actor()

        return await self.update(obj, data=column_updates)

    def _apply_conditions_to_the_query(
        self,
        query: Select,
        where_clauses: ColumnExpressionArgument | list[ColumnExpressionArgument] | None = None,
        options: list[ColumnExpressionArgument] | None = None,
        order_by: list[ColumnExpressionArgument] | str | None = None,
    ) -> Select:
        """
        Applies default options and extra conditions to the query.

        Args:
            query (Select): The query to modify.
            where_clauses (list[ColumnExpressionArgument] | None): Additional query conditions.

        Returns:
            Select: The modified query.
        """
        if where_clauses:
            query = query.where(*where_clauses)
        orm_options = (self.default_options or []) + (options or [])
        if order_by:
            if isinstance(order_by, str):
                if hasattr(self.model_cls, order_by):
                    query = query.order_by(getattr(self.model_cls, order_by))
                else:
                    raise ValueError(f"Invalid column name: {order_by}")
            elif isinstance(order_by, list):
                query = query.order_by(*order_by)
            else:
                raise TypeError("order_by must be a string or a list of ColumnExpressionArgument.")
        if orm_options:
            query = query.options(*orm_options)
        return query

    async def query_db(
        self,
        where_clauses: Sequence[ColumnExpressionArgument | Exists] | None = None,
        limit: int | None = 50,
        offset: int = 0,
        all_results: bool | None = False,
        order_by: str | None = None,
        options: list[ORMOption] | None = None,
    ) -> Sequence[M]:
        """
                Executes a database query with filtering, pagination, ordering, and options.

        This method allows for querying the database with conditions, applying additional
        filters, controlling pagination, ordering results, and enabling optional query options.

        Args:
            conditions (Any):
                - Positional filtering conditions applied using `.where()`.
                - Example: `User.status == "active"`, `User.age > 18`.

            where_clauses (Sequence[ColumnExpressionArgument | Exists] | None, optional):
                - Additional conditions applied using `.where()`.
                - Useful for combining multiple filters dynamically.
                - Default is `None`.

            limit (int | None, optional):
                - Maximum number of results to return.
                - If `None`, retrieves all results.
                - Default is `50`.

            offset (int, optional):
                - Number of records to skip for pagination.
                - Default is `0`.

            all_results (bool | None, optional):
                - If `True`, overrides `limit` and fetches all results.
                - Default is `False`.

            order_by (str | None, optional):
                - Column name used to order the results.
                - Default is `"id"`.

            options (list[ORMOption] | None, optional):
                - SQLAlchemy ORM options to modify query behavior
                (e.g., `joinedload` for relationships).
                - Default is `None`.

        Returns:
            Sequence[M]:
                - A list of objects matching the query.
                - If no records are found, returns an empty list.

        """
        if (limit or offset) and all_results:
            raise InvalidParameters("Please specify either limit or offset, or all_results.")
        # default query
        query = select(self.model_cls)
        # add the default options, if any
        query = self._apply_conditions_to_the_query(
            query=query, where_clauses=where_clauses, options=options, order_by=order_by
        )
        if not all_results:
            # apply limit and offset
            query = query.offset(offset).limit(limit)
        results = await self.session.execute(query)
        return results.scalars().unique().all()

    async def stream_scalars(
        self,
        extra_conditions: list[ColumnExpressionArgument] | None = None,
        order_by: list[ColumnExpressionArgument] | None = None,
        batch_size: int = 100,
    ) -> AsyncGenerator[M, None]:
        query = select(self.model_cls)
        query = self._apply_conditions_to_the_query(
            query=query, where_clauses=extra_conditions, order_by=order_by
        )
        result = await self.session.stream_scalars(
            query,
            execution_options={"yield_per": batch_size},
        )
        async for row in result:
            yield row
        await result.close()

    async def count(
        self,
        where_clauses: list[ColumnExpressionArgument] | None = None,
    ) -> int:
        """
        Counts the number of objects matching the given conditions.

        Args:
            *where_clauses (ColumnExpressionArgument): Filtering conditions.

        Returns:
            int: The count of matching records.
        """
        query = select(func.count(self.model_cls.id))
        if where_clauses:
            query = query.where(*where_clauses)
        result = await self.session.execute(query)
        return result.scalars().one()

    async def first(
        self,
        where_clauses: list[ColumnExpressionArgument] | None = None,
    ) -> M | None:
        query = select(self.model_cls).where(*where_clauses)
        query = self._apply_conditions_to_the_query(query=query)

        result = await self.session.execute(query)
        return result.scalars().first()

    async def _get_model_obj(self, id_or_obj: str | M) -> M:
        if isinstance(id_or_obj, str):
            return await self.get(id_or_obj)

        return id_or_obj

    async def _save_changes(self, obj: M):
        try:
            await self.session.flush()
        except IntegrityError as e:
            raise ConstraintViolationError(
                f"Failed to save changes to {self.model_cls.__name__}: {e}."
            ) from e
        await self.session.refresh(obj)


class EntitlementHandler(ModelHandler[Entitlement]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(Entitlement.owner),
            joinedload(Entitlement.created_by),
            joinedload(Entitlement.updated_by),
            joinedload(Entitlement.redeemed_by),
        ]

    async def terminate(self, entitlement: Entitlement) -> Entitlement:
        return await self.update(
            entitlement.id,
            data={
                "status": EntitlementStatus.TERMINATED,
                "terminated_at": datetime.now(UTC),
                "terminated_by": auth_context.get().get_actor(),
            },
        )


class OrganizationHandler(ModelHandler[Organization]):
    pass


class SystemHandler(ModelHandler[System]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(System.owner),
            joinedload(System.created_by),
            joinedload(System.updated_by),
            joinedload(System.deleted_by),
        ]


class AccountHandler(ModelHandler[Account]):
    pass


class UserHandler(ModelHandler[User]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(User.last_used_account),
            joinedload(User.created_by),
            joinedload(User.updated_by),
            joinedload(User.deleted_by),
        ]


class AccountUserHandler(ModelHandler[AccountUser]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(AccountUser.account),
            joinedload(AccountUser.user),
        ]

    async def delete_by_user(self, user_id: str):
        """
        Updates the status of the AccountUser that belongs to the user
        identified by the given user_id, to DELETE.
        """
        actor_obj = auth_context.get().get_actor() if auth_context.get() else None
        actor_id = getattr(actor_obj, "id", None)
        stmt = (
            update(AccountUser)
            .where(AccountUser.status != AccountUserStatus.DELETED, AccountUser.user_id == user_id)
            .values(
                status=AccountUserStatus.DELETED,
                deleted_at=datetime.now(UTC),
                deleted_by_id=actor_id,
                # Explicitly set the relationship key
                # value instead of setting the expected `deleted_at` field. Setting the deleted_by
                # causes an error due to a misinterpreted query that puts the deleted_at field
                # expecting a boolean value
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_account_user(
        self,
        account_id: str,
        user_id: str,
        extra_conditions: list[ColumnExpressionArgument] | None = None,
    ) -> AccountUser | None:
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
