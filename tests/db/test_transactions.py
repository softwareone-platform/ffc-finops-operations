import random
import secrets
import uuid
from logging import DEBUG

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.handlers import EntitlementHandler, SystemHandler
from app.db.models import Entitlement, System
from app.enums import DatasourceType


def random_entitlement() -> Entitlement:
    return Entitlement(
        sponsor_name=random.choice(list(DatasourceType)),
        sponsor_external_id=str(uuid.uuid4()),
        sponsor_container_id=str(uuid.uuid4()),
    )


def random_system() -> System:
    return System(
        name=str(uuid.uuid4()),
        external_id=str(uuid.uuid4()),
        jwt_secret=secrets.token_hex(32),
    )


def get_sql_query_types(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        first_word
        for record in caplog.records
        if (first_word := record.message.split()[0]).isupper()
    ]


# ==========================
# Using the session directly
# ==========================


async def test_simple_insert(db_session: AsyncSession, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        db_session.add(random_entitlement())
        await db_session.commit()

    assert get_sql_query_types(caplog) == ["BEGIN", "INSERT", "COMMIT"]


async def test_two_inserts_same_model_explicit_commit(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        db_session.add(random_entitlement())
        db_session.add(random_entitlement())
        await db_session.commit()

    # SQLAlchemy optimises the two inserts into a single INSERT query
    assert get_sql_query_types(caplog) == ["BEGIN", "INSERT", "COMMIT"]


async def test_two_inserts_different_models_explicit_commit(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        db_session.add(random_entitlement())
        db_session.add(random_system())
        await db_session.commit()

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",  # insert entitlement
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
    ]


async def test_two_inserts_different_models_two_explicit_commits(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        db_session.add(random_entitlement())
        await db_session.commit()

        db_session.add(random_system())
        await db_session.commit()

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",  # insert entitlement
        "COMMIT",
        "BEGIN",
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
    ]


async def test_two_inserts_different_models_session_begin(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        async with db_session.begin():
            db_session.add(random_entitlement())
            db_session.add(random_system())

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",  # insert entitlement
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
    ]


async def test_explicit_commit_then_session_begin(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        db_session.add(random_entitlement())
        await db_session.commit()

        async with db_session.begin():
            db_session.add(random_entitlement())
            db_session.add(random_system())

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",  # insert entitlement #1
        "COMMIT",
        "BEGIN",
        "INSERT",  # insert entitlement #2
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
    ]


# ==================
# Using the handlers
# ==================


async def test_handler_simple_insert(db_session: AsyncSession, caplog: pytest.LogCaptureFixture):
    entitlements_handler = EntitlementHandler(db_session)

    entitlement = random_entitlement()

    assert entitlement.id is None

    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        await entitlements_handler.create(entitlement)

    assert entitlement.id is not None

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_simple_insert_two_objects(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    entitlements_handler = EntitlementHandler(db_session)

    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        await entitlements_handler.create(random_entitlement())
        await entitlements_handler.create(random_entitlement())

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_insert_two_models(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    entitlements_handler = EntitlementHandler(db_session)
    systems_handler = SystemHandler(db_session)

    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        await entitlements_handler.create(random_entitlement())
        await systems_handler.create(random_system())

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_insert_two_models_with_session_begin(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    entitlements_handler = EntitlementHandler(db_session)
    systems_handler = SystemHandler(db_session)

    with caplog.at_level(DEBUG, logger="sqlalchemy.engine.Engine"):
        async with db_session.begin():
            await entitlements_handler.create(random_entitlement())
            await systems_handler.create(random_system())

    assert get_sql_query_types(caplog) == [
        "BEGIN",
        "INSERT",
        "SELECT",
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "SELECT",
        "COMMIT",
    ]
