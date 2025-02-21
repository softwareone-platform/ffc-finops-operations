from types import TracebackType
from typing import Any

from sqlalchemy import Connection, event
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.ext.asyncio import AsyncEngine


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
