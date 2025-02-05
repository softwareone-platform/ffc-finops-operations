import pytest
import sqlalchemy as sa
import sqlalchemy.ext.asyncio
import sqlalchemy.ext.declarative
from sqlalchemy import ForeignKey, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from tests.pytest_plugins.capsql import SQLAlchemyCapturer


# Set up models used only for testing
class TestingBaseModel(DeclarativeBase):
    __test__ = False  # Prevent pytest from trying to collect this class


class Order(TestingBaseModel):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipient: Mapped[str]
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(TestingBaseModel):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_name: Mapped[str]
    price: Mapped[float]
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    order: Mapped[Order] = relationship(back_populates="items")


@pytest.fixture(scope="module", autouse=True)
async def create_testing_tables(db_engine: sa.ext.asyncio.AsyncEngine):
    try:
        async with db_engine.begin() as conn:
            await conn.run_sync(TestingBaseModel.metadata.create_all)

        yield db_engine
    finally:
        async with db_engine.begin() as conn:
            await conn.run_sync(TestingBaseModel.metadata.drop_all)

        await db_engine.dispose()


async def test_simple_select(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    await db_session.execute(text("SELECT 1"))

    capsql.assert_query_types("BEGIN", "SELECT")
    capsql.assert_query_count(2)


@pytest.mark.parametrize(
    ("include_transaction_queries", "expected_query_count"),
    [
        (True, 9),
        (False, 5),
    ],
)
async def test_assert_query_count(
    db_session: AsyncSession,
    capsql: SQLAlchemyCapturer,
    include_transaction_queries: bool,
    expected_query_count: int,
):
    await db_session.execute(text("SELECT 1"))
    await db_session.execute(select(OrderItem))

    await db_session.commit()

    async with db_session.begin():
        await db_session.execute(select(Order).where(Order.id == 1))
        await db_session.execute(select(text("1")))

        db_session.add(Order(recipient="John Doe"))

    capsql.assert_query_count(
        expected_query_count, include_transaction_queries=include_transaction_queries
    )


async def test_simple_insert(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    order = Order(recipient="John Doe")

    db_session.add(order)
    await db_session.commit()

    capsql.assert_query_types(
        "BEGIN",
        "INSERT",
        "COMMIT",
    )

    insert_expr = capsql.captured_expressions[1]
    assert insert_expr.executable.is_insert
    assert insert_expr.executable.table.name == Order.__tablename__  # type: ignore[attr-defined]
    assert insert_expr.get_sql() == "INSERT INTO orders (recipient) VALUES (:recipient)"
    assert insert_expr.params == {"recipient": "John Doe"}

    assert (
        insert_expr.get_sql(bind_params=True)
        == "INSERT INTO orders (recipient) VALUES ('John Doe')"
    )

    capsql.assert_captured_queries(
        "BEGIN",
        "INSERT INTO orders (recipient) VALUES (:recipient)",
        "COMMIT",
    )

    capsql.assert_captured_queries(
        "INSERT INTO orders (recipient) VALUES ('John Doe')",
        include_transaction_queries=False,
        bind_params=True,
    )


async def test_insert_with_relationship(db_session: AsyncSession, capsql: SQLAlchemyCapturer):
    async with db_session.begin():
        order = Order(recipient="John Doe")
        db_session.add(order)
        db_session.add(OrderItem(item_name="Bread", price=2.00, order=order))
        db_session.add(OrderItem(item_name="Butter", price=3.50, order=order))

    capsql.assert_captured_queries(
        "INSERT INTO orders (recipient) VALUES ('John Doe')",
        "INSERT INTO order_items (item_name, price, order_id) VALUES ('Bread', 2.0, 1), ('Butter', 3.5, 1)",  # noqa: E501
        include_transaction_queries=False,
        bind_params=True,
    )
