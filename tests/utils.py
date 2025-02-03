from types import TracebackType
from typing import Any

from sqlalchemy import Connection, event
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.ext.asyncio import AsyncEngine

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
