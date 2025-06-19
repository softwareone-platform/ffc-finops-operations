import asyncio
import logging
from collections.abc import Sequence
from typing import Annotated, Any

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_clients.exchange_rate import ExchangeRateAPIClient
from app.conf import Settings
from app.db.base import session_factory
from app.db.handlers import ExchangeRatesHandler
from app.db.models import ExchangeRates, Organization
from app.notifications import send_exception, send_info
from app.telemetry import capture_telemetry_cli_command

logger = logging.getLogger(__name__)


async def fetch_unique_currencies(session: AsyncSession) -> Sequence[str]:
    logger.info("Fetching all the unique currencies from the database")

    currencies_stmt = select(Organization.currency).distinct().order_by(Organization.currency.asc())

    currencies = (await session.scalars(currencies_stmt)).all()

    logger.info(
        "Found the following unique currencies from the database: %s", ", ".join(currencies)
    )
    return currencies


async def get_currencies_to_update(session: AsyncSession) -> list[str]:
    exchange_rates_handler = ExchangeRatesHandler(session)
    all_currencies = await fetch_unique_currencies(session)

    currencies_to_update = []

    latest_exchange_rates = {
        exchange_rates.base_currency: exchange_rates
        for exchange_rates in await exchange_rates_handler.fetch_latest_valid()
    }

    for base_currency in all_currencies:
        if base_currency in latest_exchange_rates:
            logger.info(
                "Exchange rates for %s are already stored in the database and are still valid, "
                "skipping feching them",
                base_currency,
            )
            continue

        logger.info(
            "Exchange rates for %s are not stored in the database or are no longer valid, "
            "adding the currency to the list to be fetched",
            base_currency,
        )

        currencies_to_update.append(base_currency)

    if currencies_to_update:
        logger.info(
            "The following currencies will be updated with their latest exchange rates: %s",
            ", ".join(currencies_to_update),
        )

    return currencies_to_update


@capture_telemetry_cli_command(__name__, "Update Latest Exchange Rates")
async def main(settings: Settings, currency: str | None = None) -> None:
    async with session_factory() as session:
        if currency:
            currencies_to_update = [currency]
        else:
            async with session.begin():
                currencies_to_update = await get_currencies_to_update(session)

            if not currencies_to_update:
                logger.info("No currencies to update, exiting")
                return

        exchange_rates_per_currency: dict[str, dict[str, Any]] = {}

        async with ExchangeRateAPIClient(settings) as exchange_rate_client:
            for base_currency in currencies_to_update:
                logger.info("Fetching latest exchange rates for %s", base_currency)

                try:
                    response = await exchange_rate_client.get_latest_rates(base_currency)
                except Exception as e:
                    msg = f"Failed to fetch exchange rates for {base_currency} due to an exception"
                    logger.exception(msg)
                    await send_exception("Exchange Rates Update Error", f"{msg}: {e}")
                    continue

                logger.info("Successfully fetched exchange rates for %s", base_currency)
                exchange_rates_per_currency[base_currency] = response.json()

        async with session.begin():
            for base_currency, api_response in exchange_rates_per_currency.items():
                logger.info("Storing latest exchange rates for %s into the database", base_currency)

                exchange_rates_model = ExchangeRates(api_response=api_response)
                session.add(exchange_rates_model)

        if exchange_rates_per_currency:
            msg = (
                f"Exchange rates for {', '.join(sorted(exchange_rates_per_currency.keys()))}"
                " stored."
            )
            logger.info(msg)
            await send_info("Exchange Rates Update Success", msg)


def command(
    ctx: typer.Context,
    currency: Annotated[
        str | None,
        typer.Option(
            "--currency",
            help="If set, fetch exchange rates for this currency only",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Fetch exahnge rates from the exchange rate API and store them in the database"""
    logger.info("Starting command function")
    asyncio.run(main(ctx.obj, currency))
    logger.info("Completed command function")
