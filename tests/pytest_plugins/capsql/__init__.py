from collections.abc import Generator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.pytest_plugins.capsql.capturer import SQLAlchemyCapturer
from tests.pytest_plugins.capsql.context import SQLAlchemyCaptureContext


@pytest.fixture
def capsql_context(db_engine: AsyncEngine) -> Generator[SQLAlchemyCaptureContext]:
    with SQLAlchemyCaptureContext(db_engine) as capsql_ctx:
        yield capsql_ctx


@pytest.fixture()
def capsql(capsql_context: SQLAlchemyCaptureContext):
    return SQLAlchemyCapturer(capsql_context)
