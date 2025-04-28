import json
from decimal import Decimal
from typing import Final, Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.handlers import ExchangeRatesHandler
from app.db.models import ExchangeRates

type Number = int | float | Decimal


class CurrencyConverterError(Exception):
    pass


class MissingExchangeRateError(CurrencyConverterError):
    def __init__(self, from_currency: str, to_currency: str) -> None:
        self.from_currency = from_currency
        self.to_currency = to_currency
        super().__init__(
            f"Missing exchange rate for {from_currency} -> {to_currency} "
            f"or {to_currency} -> {from_currency}"
        )


class CurrencyConverter:
    DECIMAL_PRECISION: Final[int] = 4

    def __init__(self, exchange_rates_per_currency: dict[str, ExchangeRates]) -> None:
        self.exchange_rates_per_currency = exchange_rates_per_currency

    @classmethod
    async def from_db(cls, db_session: AsyncSession) -> Self:
        exchange_rates_handler = ExchangeRatesHandler(db_session)
        exchange_rates = await exchange_rates_handler.fetch_latest_valid()

        if not exchange_rates:
            raise CurrencyConverterError("No active exchange rates found in the database")

        return cls({er.base_currency: er for er in exchange_rates})

    @classmethod
    def _normalize(cls, amount: Number) -> Decimal:
        q = Decimal("10") ** -cls.DECIMAL_PRECISION

        if isinstance(amount, int | float):
            return Decimal(amount).quantize(q)

        return amount.quantize(q)

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> Decimal:
        if from_currency == to_currency:
            return self._normalize(1)

        # If we have exchange rates for the from_currency as the base currency, use that
        if (exchange_rates := self.exchange_rates_per_currency.get(from_currency)) is not None:
            conversion_rate = exchange_rates.api_response["conversion_rates"].get(to_currency)

            if conversion_rate is not None:
                return self._normalize(conversion_rate)

        # Otherwise, check if we have exchange rates in the oposite direction,
        # i.e. to_currency as the base currency
        if (exchange_rates := self.exchange_rates_per_currency.get(to_currency)) is not None:
            conversion_rate = exchange_rates.api_response["conversion_rates"].get(from_currency)

            if conversion_rate is not None:
                return self._normalize(1 / conversion_rate)

        raise MissingExchangeRateError(from_currency, to_currency)

    def convert_currency(self, amount: Number, from_currency: str, to_currency: str) -> Decimal:
        amount = self._normalize(amount)

        if amount == 0 or from_currency == to_currency:
            return amount

        exchange_rate = self.get_exchange_rate(from_currency, to_currency)
        return self._normalize(amount * exchange_rate)

    def get_exchangerate_api_response_json(self, base_currency: str) -> str:
        if base_currency not in self.exchange_rates_per_currency is None:  # pragma: no branch
            raise CurrencyConverterError(
                f"No exchange rates found for {base_currency} in the database"
            )

        return json.dumps(self.exchange_rates_per_currency[base_currency].api_response, indent=4)
