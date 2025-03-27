import asyncio
import logging

import typer

from app.api_clients.exchange_rate import ExchangeRateAPIClient
from app.conf import Settings
from app.db.base import session_factory
from app.db.handlers import ExchangeRatesHandler
from app.db.models import ExchangeRates

logger = logging.getLogger(__name__)


async def main(settings: Settings) -> None:
    async with session_factory() as session:
        exchange_rates_handler = ExchangeRatesHandler(session)

        async with session.begin():
            latest_exchange_rates = await exchange_rates_handler.fetch_latest_valid()

            if latest_exchange_rates is not None:
                logger.info("Exchange rates are already stored in the database and are still valid")
                logger.info("Skipping fetching exchange rates")
                return

            logger.info("Exchange rates are not stored in the database or are no longer valid")

        logger.info("Fetching latest exchange rates against USD")
        async with ExchangeRateAPIClient(settings) as exchange_rate_client:
            try:
                response = await exchange_rate_client.get_latest_rates(base_currency="USD")
            except Exception as e:
                logger.exception("Failed to fetch exchange rates due to an exception")
                raise e

            exchange_rates = response.json()

        logger.info("Successfully fetched exchange rates")

        logger.info("Storing latest exchange rates into the database")
        async with session.begin():
            exchange_rates_model = ExchangeRates(api_response=exchange_rates)
            session.add(exchange_rates_model)

        logger.info("Completed storing exchange rates")


def command(ctx: typer.Context) -> None:
    """Fetch exahnge rates from the exchange rate API and store them in the database"""
    logger.info("Starting command function")
    asyncio.run(main(ctx.obj))
    logger.info("Completed command function")
