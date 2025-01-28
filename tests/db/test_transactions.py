import random
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_tx_db_session
from app.db.handlers import EntitlementHandler, SystemHandler
from app.db.models import Entitlement, System
from app.enums import DatasourceType
from tests.utils import SQLAlchemyCapturer


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


def get_sql_query_types(statements: list[str]) -> list[str]:
    return [
        first_word for statement in statements if (first_word := statement.split()[0]).isupper()
    ]


# ==================
# Using the handlers
# ==================


async def test_handler_simple_insert(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    entitlements_handler = EntitlementHandler(db_session)

    entitlement = random_entitlement()

    assert entitlement.id is None

    with capsql:
        await entitlements_handler.create(entitlement)

    assert entitlement.id is not None

    assert get_sql_query_types(capsql.statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_simple_insert_two_objects(
    db_session: AsyncSession, capsql: SQLAlchemyCapturer
):
    entitlements_handler = EntitlementHandler(db_session)

    with capsql:
        await entitlements_handler.create(random_entitlement())
        await entitlements_handler.create(random_entitlement())

    assert get_sql_query_types(capsql.statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
        "SELECT",
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_insert_two_models(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    entitlements_handler = EntitlementHandler(db_session)
    systems_handler = SystemHandler(db_session)

    with capsql:
        await entitlements_handler.create(random_entitlement())
        await systems_handler.create(random_system())

    assert get_sql_query_types(capsql.statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",  # check PK
        "SELECT",  # check PK
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_insert_two_models_with_session_begin(capsql: SQLAlchemyCapturer):
    with capsql:
        async with get_tx_db_session() as tx_session:
            entitlements_handler = EntitlementHandler(tx_session)
            systems_handler = SystemHandler(tx_session)
            await entitlements_handler.create(random_entitlement())
            await systems_handler.create(random_system())

    assert get_sql_query_types(capsql.statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "SELECT",  # check PK
        "SELECT",  # check PK
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "SELECT",
        "COMMIT",
    ]


async def test_handler_insert_two_models_with_session_begin_rollback(capsql: SQLAlchemyCapturer):
    with capsql:
        try:
            async with get_tx_db_session() as tx_session:
                entitlements_handler = EntitlementHandler(tx_session)
                systems_handler = SystemHandler(tx_session)
                await entitlements_handler.create(random_entitlement())
                await systems_handler.create(random_system())
                raise Exception("rollback!")
        except Exception:
            pass

    assert get_sql_query_types(capsql.statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "SELECT",  # check PK
        "SELECT",  # check PK
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "SELECT",
        "ROLLBACK",
    ]


async def test_handler_insert_two_models_with_session_begin_multiple_transactions(
    capsql: SQLAlchemyCapturer,
):
    statements = []
    with capsql:
        async with get_tx_db_session() as tx_session:
            entitlements_handler = EntitlementHandler(tx_session)
            systems_handler = SystemHandler(tx_session)
            await entitlements_handler.create(random_entitlement())
            await systems_handler.create(random_system())

    statements.extend(capsql.statements)

    with capsql:
        async with get_tx_db_session() as tx_session:
            entitlements_handler = EntitlementHandler(tx_session)
            systems_handler = SystemHandler(tx_session)
            await entitlements_handler.create(random_entitlement())
            await systems_handler.create(random_system())

    statements.extend(capsql.statements)

    assert get_sql_query_types(statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "SELECT",  # check PK
        "SELECT",  # check PK
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "SELECT",
        "COMMIT",
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "SELECT",  # check PK
        "SELECT",  # check PK
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "SELECT",
        "COMMIT",
    ]
