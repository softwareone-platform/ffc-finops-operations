from decimal import Decimal
from typing import Final, Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.handlers import ExchangeRatesHandler

type Number = int | float | Decimal


class CurrencyConverterError(Exception):
    pass


class MissingExchangeRateError(CurrencyConverterError):
    def __init__(self, currency: str) -> None:
        self.currency = currency
        super().__init__(f"Missing exchange rate for currency {currency}")


class CurrencyConverter:
    DECIMAL_PRECISION: Final[int] = 4

    def __init__(self, base_currency: str, exchange_rates: dict[str, Decimal]) -> None:
        self.base_currency = base_currency
        self.exchange_rates = exchange_rates

    @classmethod
    async def from_db(cls, db_session: AsyncSession) -> Self:
        exchange_rates_handler = ExchangeRatesHandler(db_session)
        exchange_rates = await exchange_rates_handler.fetch_latest_valid()

        if exchange_rates is None:
            raise CurrencyConverterError("No active exchange rates found in the database")

        conversion_rate: dict[str, Decimal] = {
            currency: cls._normalize(rate)
            for currency, rate in exchange_rates.api_response["conversion_rates"].items()
        }
        return cls(exchange_rates.base_currency, conversion_rate)

    @classmethod
    def _normalize(cls, amount: Number) -> Decimal:
        q = Decimal("10") ** -cls.DECIMAL_PRECISION

        if isinstance(amount, int | float):
            return Decimal(amount).quantize(q)

        return amount.quantize(q)

    def _get_exchange_rate_against_base(self, currency: str) -> Decimal:
        if currency == self.base_currency:
            return self._normalize(1)

        try:
            return self.exchange_rates[currency]
        except KeyError:
            raise MissingExchangeRateError(currency)

    def convert_currency(self, amount: Number, from_currency: str, to_currency: str) -> Decimal:
        amount = self._normalize(amount)

        if amount == 0 or from_currency == to_currency:
            return amount

        to_currency_rate = self._get_exchange_rate_against_base(to_currency)
        from_currency_rate = self._get_exchange_rate_against_base(from_currency)

        return self._normalize(amount * to_currency_rate / from_currency_rate)
