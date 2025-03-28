from datetime import UTC, datetime
from decimal import Decimal

import pytest
import time_machine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.currency import CurrencyConverter, CurrencyConverterError, MissingExchangeRateError
from app.db.models import ExchangeRates
from tests.types import ModelFactory


@pytest.fixture
def currency_converter() -> CurrencyConverter:
    return CurrencyConverter(
        base_currency="USD",
        exchange_rates={
            "EUR": Decimal("0.9252"),
            "GBP": Decimal("0.7737"),
        },
    )


async def test_currency_converter_from_db(
    db_session: AsyncSession,
    exchange_rates_factory: ModelFactory[ExchangeRates],
):
    exchange_rates = await exchange_rates_factory(
        base_currency="USD",
        exchange_rates={
            "USD": 1.0,
            "EUR": 0.9252,
            "GBP": 0.7737,
        },
    )

    currency_converter = await CurrencyConverter.from_db(db_session)
    assert currency_converter.base_currency == exchange_rates.base_currency
    assert currency_converter.exchange_rates == {
        ccy: Decimal(rate).quantize(Decimal("0.1") ** CurrencyConverter.DECIMAL_PRECISION)
        for ccy, rate in exchange_rates.api_response["conversion_rates"].items()
    }


async def test_currency_converter_from_db_no_db_records(db_session: AsyncSession):
    assert (await db_session.scalar(select(ExchangeRates))) is None

    with pytest.raises(
        CurrencyConverterError, match="No active exchange rates found in the database"
    ):
        await CurrencyConverter.from_db(db_session)


@time_machine.travel("2025-03-28T10:00:00Z", tick=False)
async def test_currency_converter_from_db_only_old_records(
    db_session: AsyncSession,
    exchange_rates_factory: ModelFactory[ExchangeRates],
):
    await exchange_rates_factory(
        last_update=datetime(2020, 1, 1, tzinfo=UTC),
        next_update=datetime(2020, 1, 2, tzinfo=UTC),
    )

    with pytest.raises(
        CurrencyConverterError, match="No active exchange rates found in the database"
    ):
        await CurrencyConverter.from_db(db_session)


@pytest.mark.parametrize(
    ("amount", "from_currency", "to_currency", "expected"),
    [
        (100, "USD", "USD", Decimal("100.0000")),
        (100, "USD", "EUR", Decimal("92.5200")),
        (100, "EUR", "USD", Decimal("108.0847")),
        (100, "EUR", "EUR", Decimal("100.0000")),
        (100, "EUR", "GBP", Decimal("83.6252")),
        (100, "GBP", "EUR", Decimal("119.5812")),
        (0, "GBP", "EUR", Decimal("0.0000")),
        (0, "USD", "USD", Decimal("0.0000")),
        (0, "EUR", "GBP", Decimal("0.0000")),
        (0, "GBP", "GBP", Decimal("0.0000")),
        (1, "ZZZ", "ZZZ", Decimal("1.0000")),
        (0, "ZZZ", "USD", Decimal("0.0000")),
        (0, "USD", "ZZZ", Decimal("0.0000")),
    ],
    ids=lambda x: str(x),
)
def test_convert_currency_success(
    currency_converter: CurrencyConverter,
    amount: int | float | Decimal,
    from_currency: str,
    to_currency: str,
    expected: Decimal,
):
    assert currency_converter.convert_currency(amount, from_currency, to_currency) == expected


@pytest.mark.parametrize(
    ("amount", "from_currency", "to_currency", "exception_cls", "exception_msg_match"),
    [
        (1, "USD", "ZZZ", MissingExchangeRateError, "ZZZ"),
        (1, "ZZZ", "USD", MissingExchangeRateError, "ZZZ"),
    ],
)
def test_convert_currency_errors(
    currency_converter: CurrencyConverter,
    amount: int | float | Decimal,
    from_currency: str,
    to_currency: str,
    exception_cls: type[CurrencyConverterError],
    exception_msg_match: str,
):
    with pytest.raises(exception_cls, match=exception_msg_match):
        currency_converter.convert_currency(amount, from_currency, to_currency)
