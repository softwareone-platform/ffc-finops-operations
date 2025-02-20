from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import sqlalchemy
from sqlalchemy import ColumnExpressionArgument, Row, RowMapping, Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import ORMOption

from app.auth.context import auth_context
from app.db.base import AsyncTxSession
from app.db.db_manager.helpers.exceptions import (
    CannotDeleteError,
    ConstraintViolationError,
    InvalidParameters,
    NotFoundError,
)
from app.db.models import (
    AuditableMixin,
    TimestampMixin,
)
from app.db.models import Base as BaseModel


def _populate_updated_by_field(obj: AuditableMixin) -> None:
    """
    Populates the `updated_by` field on the object.

    Args:
        obj (AuditableMixin): The object to update.
    """
    with suppress(LookupError):
        obj.updated_by = auth_context.get().get_actor()


def _populate_auditable_fields(obj: AuditableMixin) -> None:
    """
    Populates auditable fields on the object.

    Args:
        obj (AuditableMixin): The object to update.
    """
    with suppress(LookupError):
        if obj.created_by is None:
            obj.created_by = auth_context.get().get_actor()
        if obj.updated_by is None:
            obj.updated_by = auth_context.get().get_actor()


class ModelHandler[M: BaseModel]:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.commit = not isinstance(self.session, AsyncTxSession)
        self.default_options: list[ORMOption] = []

    @classmethod
    def _get_generic_cls_args(cls):
        """
        Returns:
           tuple[type[M], ...]: The generic class arguments for the model handler.
        """
        return next(
            base_cls.__args__
            for base_cls in cls.__orig_bases__
            if base_cls.__origin__ is ModelHandler
        )

    @property
    def model_cls(self) -> type[M]:
        """
        Resolves the model class type dynamically.

        Returns:
            type[M]: The model class type.
        """
        return self._get_generic_cls_args()[0]

    async def _get_model_obj(self, id_or_obj: str | M) -> M:
        if isinstance(id_or_obj, str):
            return await self.query_by_id(id_or_obj)

        return id_or_obj

    async def _save_changes(self, obj: M):
        try:
            if self.commit:
                await self.session.commit()
            else:
                await self.session.flush()
        except IntegrityError as e:
            raise ConstraintViolationError(
                f"Failed to save changes to {self.model_cls.__name__}: {e}."
            ) from e
        await self.session.refresh(obj)

    def _apply_conditions_and_options_to_the_query(
        self,
        query: Select,
        extra_conditions: list[ColumnExpressionArgument] | None = None,
    ) -> Select:
        """
        Applies default options and extra conditions to the query.

        Args:
            query (Select): The query to modify.
            extra_conditions (list[ColumnExpressionArgument] | None): Additional query conditions.

        Returns:
            Select: The modified query.
        """
        if extra_conditions:
            query = query.where(*extra_conditions)
        if self.default_options:
            query = query.options(*self.default_options)
        return query

    async def store_data(self, obj: M) -> M:
        """
        Creates and saves a new object in the database.

        Args:
            obj (M): The object to be created.

        Returns:
            M: The created object.
        """
        if isinstance(obj, AuditableMixin):  # pragma: no branch
            _populate_auditable_fields(obj)

        try:
            self.session.add(obj)
            await self._save_changes(obj)
        except IntegrityError as e:
            raise ConstraintViolationError(
                f"Failed to create {self.model_cls.__name__}: {e}."
            ) from e

        return obj

    async def query_by_id(
        self, id: str, extra_conditions: list[ColumnExpressionArgument] | None = None
    ) -> M:
        query = select(self.model_cls).where(self.model_cls.id == id)
        # Apply default options
        query = self._apply_conditions_and_options_to_the_query(query, extra_conditions)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()

        if instance is None:
            raise NotFoundError(f"{self.model_cls.__name__} with ID `{str(id)}` wasn't found.")

        return instance

    async def get_or_create(
        self, *, defaults: dict[str, Any] | None = None, **filters: Any
    ) -> tuple[Row[Any] | RowMapping, bool] | tuple[Any, bool]:
        """
        Retrieves or creates an object based on the filters.

        Args:
            defaults (dict[str, Any] | None): Default values for the new object.
            filters (Any): Filters to search for the object.

        Returns:
            tuple[M, bool]: The object and a boolean indicating if it was created.
        """
        defaults = defaults or {}
        query = select(self.model_cls).where(
            *(getattr(self.model_cls, key) == value for key, value in filters.items())
        )
        # Apply default options
        query = self._apply_conditions_and_options_to_the_query(query)
        result = await self.session.execute(query)
        obj = result.scalars().first()

        if obj:
            return obj, False

        params = filters
        params.update(defaults)

        obj = await self.store_data(self.model_cls(**params))
        return obj, True

    async def update(self, id_or_obj: str | M, data: dict[str, Any]) -> M:
        """
        Updates an object with the provided data.

        Args:
            id_or_obj (str | M): The ID or object to update.
            data (dict[str, Any]): The data to update.

        Returns:
            M: The updated object.
        """
        obj = await self._get_model_obj(id_or_obj)

        for key, value in data.items():
            setattr(obj, key, value)

        if isinstance(obj, AuditableMixin) and "updated_by" not in data:  # pragma: no branch
            _populate_updated_by_field(obj)

        await self._save_changes(obj)
        return obj

    async def soft_delete(self, id_or_obj: str | M) -> None:
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
            with suppress(LookupError):
                column_updates["deleted_by"] = auth_context.get().get_actor()

        await self.update(obj, column_updates)

    async def query_db(
        self,
        conditions: Any | None = None,
        limit: int | None = 50,
        offset: int = 0,
        all_results: bool | None = False,
        order_by: str | None = "id",
    ) -> Sequence[M]:
        if (limit or offset) and all_results:
            raise InvalidParameters("Please specify either limit or offset, or all_results.")
        # default query
        query = select(self.model_cls)

        # process optional conditions
        if conditions:
            query = query.where(*conditions)
        # add the default options, if any
        query = self._apply_conditions_and_options_to_the_query(query)
        # apply order_by
        query = query.order_by(getattr(self.model_cls, order_by))
        if not all_results:
            # apply limit and offset
            query = query.offset(offset).limit(limit)
        results = await self.session.execute(query)
        return results.scalars().all()

    async def return_query_count(self, *extra_conditions: ColumnExpressionArgument) -> int:
        """
        Counts the number of objects matching the conditions.

        Args:
            extra_conditions (ColumnExpressionArgument): Query conditions.

        Returns:
            int: The count of matching objects.
        """
        query = select(func.count(self.model_cls.id))
        if extra_conditions:
            query = query.where(*extra_conditions)
        result = await self.session.execute(query)
        return result.scalars().one()

    async def query_and_return_first_occurrence(self, *conditions: Any) -> M | None:
        """
        Retrieves the first object matching the conditions.

        Args:
            conditions (Any): The query conditions.

        Returns:
            M | None: The first matching object or None.
        """
        query = select(self.model_cls).where(*conditions)
        query = self._apply_conditions_and_options_to_the_query(query)
        result = await self.session.execute(query)
        return result.scalars().first()
