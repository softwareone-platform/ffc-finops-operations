from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.currency import CurrencyConverter, CurrencyConverterError, MissingExchangeRateError
from app.db.models import ExchangeRates
from tests.types import ModelFactory


@pytest.fixture
async def currency_converter(
    db_session: AsyncSession,
    exchange_rates_factory: ModelFactory[ExchangeRates],
) -> CurrencyConverter:
    await exchange_rates_factory(
        exchange_rates={
            "USD": 1.0,
            "EUR": 0.9252,
            "GBP": 0.7737,
        }
    )

    return await CurrencyConverter.from_db(db_session)


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
        (1, "USD", "ZZZ", MissingExchangeRateError("ZZZ")),
        (1, "ZZZ", "USD", MissingExchangeRateError("ZZZ")),
        (1, "ZZZ", "ZZZ", Decimal("1.0000")),
        (0, "ZZZ", "USD", Decimal("0.0000")),
        (0, "USD", "ZZZ", Decimal("0.0000")),
    ],
)
def test_convert_currency(
    currency_converter: CurrencyConverter,
    amount: int | float | Decimal,
    from_currency: str,
    to_currency: str,
    expected: Decimal | CurrencyConverterError,
):
    if isinstance(expected, CurrencyConverterError):
        with pytest.raises(expected.__class__, match=str(expected)):
            currency_converter.convert_currency(amount, from_currency, to_currency)
    else:
        assert currency_converter.convert_currency(amount, from_currency, to_currency) == expected
