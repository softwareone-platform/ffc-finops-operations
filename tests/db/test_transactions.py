import random
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db import get_tx_db_session
from app.db.handlers import AccountHandler, EntitlementHandler, SystemHandler
from app.db.models import Account, Entitlement, System
from app.enums import DatasourceType
from tests.utils import SQLAlchemyCapturer


def random_account() -> Account:
    return Account(name=str(uuid.uuid4()), external_id=str(uuid.uuid4()))


def random_entitlement(account_id) -> Entitlement:
    return Entitlement(
        name=random.choice(list(DatasourceType)),
        affiliate_external_id=str(uuid.uuid4()),
        datasource_id=str(uuid.uuid4()),
        owner_id=account_id,
    )


def random_system(account_id) -> System:
    return System(
        name=str(uuid.uuid4()),
        external_id=str(uuid.uuid4()),
        jwt_secret=secrets.token_hex(32),
        owner_id=account_id,
    )


def get_sql_query_types(statements: list[str]) -> list[str]:
    return [
        first_word for statement in statements if (first_word := statement.split()[0]).isupper()
    ]


# ==================
# Using the handlers
# ==================


async def test_handler_simple_insert(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    account_handler = AccountHandler(db_session)

    account = random_account()
    assert account.id is None

    with capsql:
        await account_handler.create(account)

    assert account.id is not None

    assert get_sql_query_types(capsql.statements) == [
        "BEGIN",
        "SELECT",  # check PK
        "INSERT",
        "COMMIT",
        "BEGIN",
        "SELECT",
    ]


async def test_handler_insert_three_models(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    account_handler = AccountHandler(db_session)
    entitlements_handler = EntitlementHandler(db_session)
    systems_handler = SystemHandler(db_session)
    account = random_account()

    with capsql:
        account = await account_handler.create(account)
        await entitlements_handler.create(random_entitlement(account.id))
        await systems_handler.create(random_system(account.id))

    statements = get_sql_query_types(capsql.statements)
    assert statements == [
        "BEGIN",
        "SELECT",  # check account PK
        "INSERT",  # insert account
        "COMMIT",
        "BEGIN",
        "SELECT",  # refresh account
        "SELECT",  # check entitlement PK
        "INSERT",  # insert entitlement
        "COMMIT",
        "BEGIN",
        "SELECT",  # refresh entitlement
        "SELECT",  # check system PK
        "INSERT",  # insert actor
        "INSERT",  # insert system
        "COMMIT",
        "BEGIN",
        "SELECT",  # refresh system
    ]


async def test_handler_insert_two_models_with_session_begin(
    db_engine: AsyncEngine, db_session: AsyncSession, capsql: SQLAlchemyCapturer
):
    account_handler = AccountHandler(db_session)
    account = random_account()
    account = await account_handler.create(account)
    db_session.expunge_all()
    with capsql:
        async with get_tx_db_session(db_engine) as tx_session:
            entitlements_handler = EntitlementHandler(tx_session)
            systems_handler = SystemHandler(tx_session)
            await entitlements_handler.create(random_entitlement(account.id))
            await systems_handler.create(random_system(account.id))

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


async def test_handler_insert_two_models_with_session_begin_rollback(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    capsql: SQLAlchemyCapturer,
):
    account_handler = AccountHandler(db_session)
    account = random_account()
    account = await account_handler.create(account)
    with capsql:
        try:
            async with get_tx_db_session(db_engine) as tx_session:
                entitlements_handler = EntitlementHandler(tx_session)
                systems_handler = SystemHandler(tx_session)
                await entitlements_handler.create(random_entitlement(account.id))
                await systems_handler.create(random_system(account.id))
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
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    capsql: SQLAlchemyCapturer,
):
    account_handler = AccountHandler(db_session)
    account = random_account()
    account = await account_handler.create(account)
    db_session.expunge_all()
    statements = []
    with capsql:
        async with get_tx_db_session(db_engine) as tx_session:
            entitlements_handler = EntitlementHandler(tx_session)
            systems_handler = SystemHandler(tx_session)
            await entitlements_handler.create(random_entitlement(account.id))
            await systems_handler.create(random_system(account.id))

    statements.extend(capsql.statements)

    with capsql:
        async with get_tx_db_session(db_engine) as tx_session:
            entitlements_handler = EntitlementHandler(tx_session)
            systems_handler = SystemHandler(tx_session)
            await entitlements_handler.create(random_entitlement(account.id))
            await systems_handler.create(random_system(account.id))

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
