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
async def currency_converter(
    db_session: AsyncSession,
    exchange_rates_factory: ModelFactory[ExchangeRates],
) -> CurrencyConverter:
    await exchange_rates_factory(base_currency="USD")
    await exchange_rates_factory(base_currency="GBP")
    await exchange_rates_factory(base_currency="EUR")

    return await CurrencyConverter.from_db(db_session)


async def test_currency_converter_from_db(
    db_session: AsyncSession,
    exchange_rates_factory: ModelFactory[ExchangeRates],
):
    usd_exchange_rates = await exchange_rates_factory(base_currency="USD")
    gbp_exchange_rates = await exchange_rates_factory(base_currency="GBP")

    currency_converter = await CurrencyConverter.from_db(db_session)
    assert sorted(currency_converter.exchange_rates_per_currency.keys()) == ["GBP", "USD"]

    assert currency_converter.exchange_rates_per_currency["GBP"].id == gbp_exchange_rates.id
    assert currency_converter.exchange_rates_per_currency["USD"].id == usd_exchange_rates.id


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
        (100, "USD", "USD", Decimal("100.00")),
        (100, "USD", "EUR", Decimal("92.52")),
        (100, "EUR", "USD", Decimal("108.08")),
        (100, "EUR", "EUR", Decimal("100.00")),
        (100, "EUR", "GBP", Decimal("85.55")),
        (100, "GBP", "EUR", Decimal("116.89")),
        (0, "GBP", "EUR", Decimal("0.00")),
        (0, "USD", "USD", Decimal("0.00")),
        (0, "EUR", "GBP", Decimal("0.00")),
        (0, "GBP", "GBP", Decimal("0.00")),
        (1, "ZZZ", "ZZZ", Decimal("1.00")),
        (0, "ZZZ", "USD", Decimal("0.00")),
        (0, "USD", "ZZZ", Decimal("0.00")),
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


@pytest.mark.parametrize(
    ("from_currency", "to_currency", "expected"),
    [
        ("USD", "GBP", Decimal("0.7737")),
        ("GBP", "USD", Decimal("1.2925")),
        ("EUR", "GBP", Decimal("0.8555")),
        ("GBP", "EUR", Decimal("1.1689")),
        ("USD", "EUR", Decimal("0.9252")),
        ("EUR", "USD", Decimal("1.0808")),
        ("ZZZ", "ZZZ", Decimal("1.00")),
        ("ZZZ", "USD", MissingExchangeRateError("ZZZ", "USD")),
    ],
)
def test_get_exchange_rate(
    currency_converter: CurrencyConverter,
    from_currency: str,
    to_currency: str,
    expected: Decimal | Exception,
):
    if isinstance(expected, Exception):
        with pytest.raises(expected.__class__, match=str(expected)):
            currency_converter.get_exchange_rate(from_currency, to_currency)
    else:
        assert currency_converter.get_exchange_rate(from_currency, to_currency) == expected
