from collections.abc import AsyncGenerator
from types import TracebackType
from typing import Any, Self

import asyncpg
import pytest
import sqlalchemy.event
from sqlalchemy import Connection, ExecutionContext, event
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.schemas import IdSchema


def assert_json_contains_model(json: dict[str, Any], expected_schema: IdSchema) -> None:
    assert all("id" in item for item in json["items"])

    items_by_id = {item["id"]: item for item in json["items"]}

    assert str(expected_schema.id) in list(items_by_id.keys())

    expected_dict = expected_schema.model_dump(mode="json")
    actual_dict = items_by_id[str(expected_schema.id)]

    for key, actual_value in actual_dict.items():
        if key not in expected_dict:
            raise AssertionError(f"{expected_schema.__class__.__name__} has no attribute {key}")

        assert expected_dict[key] == actual_value


class SQLAlchemyCapturer:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.queries: list[str] = []
        self.statements: list[str] = []

    def clear(self) -> None:
        self.statements = []
        self.queries = []

    def on_begin(
        self,
        conn: Connection,
    ) -> None:
        self.statements.append("BEGIN")

    def on_commit(
        self,
        conn: Connection,
    ) -> None:
        self.statements.append("COMMIT")

    def on_rollback(
        self,
        conn: Connection,
    ) -> None:
        self.statements.append("ROLLBACK")

    def on_before_cursor_execute(
        self,
        conn: Connection,
        cursor: DBAPICursor,
        statement: str,
        parameters: Any,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        self.statements.append(statement)
        self.queries.append(statement)

    def __enter__(self):
        self.clear()
        event.listen(
            self.engine.sync_engine,
            "begin",
            self.on_begin,
        )
        event.listen(
            self.engine.sync_engine,
            "commit",
            self.on_commit,
        )
        event.listen(
            self.engine.sync_engine,
            "rollback",
            self.on_rollback,
        )
        event.listen(
            self.engine.sync_engine,
            "before_cursor_execute",
            self.on_before_cursor_execute,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        event.remove(
            self.engine.sync_engine,
            "begin",
            self.on_begin,
        )
        event.remove(
            self.engine.sync_engine,
            "commit",
            self.on_commit,
        )
        event.remove(
            self.engine.sync_engine,
            "rollback",
            self.on_rollback,
        )
        event.remove(
            self.engine.sync_engine,
            "before_cursor_execute",
            self.on_before_cursor_execute,
        )


class CaptureQueriesContext:
    """
    Caputre SQL queries executed in a given context.
    S̶t̶o̶l̶e̶n̶ Heavily inspired by django.test.utils.CaptureQueriesContext
    """

    connection: AsyncConnection
    captured_queries: list[str]
    enabled: bool

    def __init__(self, connection: AsyncConnection):
        self.connection = connection
        self.captured_queries = []
        self.enabled = False

    def clear(self) -> None:
        self.captured_queries = []

    async def __aenter__(self) -> Self:
        sqlalchemy.event.listen(self.connection, "after_cursor_execute", self._after_cursor_execute)
        self.enabled = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        sqlalchemy.event.remove(self.connection, "after_cursor_execute", self._after_cursor_execute)
        self.enabled = False

    async def _after_cursor_execute(
        self,
        conn: AsyncConnection,
        cursor: asyncpg.cursor.Cursor,
        statement: str,
        parameters: dict[str, Any] | tuple[Any] | list[Any] | None,
        context: ExecutionContext | None,
        executemany: bool,
    ):
        if not self.enabled:
            return

        self.captured_queries.append(sqlalchemy.text(statement).bindparams(**parameters))


class AssertDBCalls:
    def __init__(self, full_test_context: CaptureQueriesContext):
        self.full_test_context = full_test_context
        self.snapshot = snapshot
        self.partial_context: CaptureQueriesContext | None = None

    @property
    def session(self):
        return self.full_test_context.session

    async def __aenter__(self) -> Self:
        self.partial_context = CaptureQueriesContext(self.session)
        self.partial_context = await self.partial_context.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        if self.partial_context is None:
            raise RuntimeError(
                f"{self.__class__.__name__}: attempting to call __aexit__ before __aenter__"
            )

        if exc_type is None:
            self.assert_db_calls_in_context(self.partial_context)

        await self.partial_context.__aexit__(exc_type, exc_val, exc_tb)

    def __call__(self):
        return self.assert_db_calls_in_context(self.full_test_context)

    def assert_db_calls_in_context(self, queries_context: CaptureQueriesContext):
        assert queries_context.captured_queries == self.snapshot


# TODO: Add snapshot fixture support
@pytest.fixture
async def assert_db_calls(db_session: AsyncSession) -> AsyncGenerator[AssertDBCalls, None]:
    async with CaptureQueriesContext(db_session) as full_test_context:
        yield AssertDBCalls(full_test_context)
