import logging
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.api_clients.exchange_rate import ExchangeRateAPIError, ExchangeRateAPIErrorType
from app.cli import app
from app.commands import update_latest_exchange_rates
from app.conf import Settings
from app.db.handlers import ExchangeRatesHandler
from app.db.models import ExchangeRates, Organization
from tests.fixtures.mock_api_clients import MockExchangeRateAPIClient
from tests.types import ModelFactory


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_successful_fetch_exchange_rates_when_missing_multiple_currencies(
    organization_factory: ModelFactory[Organization],
    exchange_rates_per_currency: dict[str, dict[str, float]],
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    time_machine: time_machine.TimeMachineFixture,
    caplog: pytest.LogCaptureFixture,
):
    await organization_factory(currency="USD", operations_external_id="ORG-123")
    # intentional duplicate to test that we only fetch USD exchange rates once
    await organization_factory(currency="USD", operations_external_id="ORG-456")
    await organization_factory(currency="GBP", operations_external_id="ORG-789")
    await organization_factory(currency="EUR", operations_external_id="ORG-987")

    exchange_rates_handler = ExchangeRatesHandler(db_session)

    existing_exchange_rates = await exchange_rates_handler.query_db()
    assert len(existing_exchange_rates) == 0

    for base_currency in exchange_rates_per_currency:
        mock_exchange_rate_api_client.mock_get_latest_rates(base_currency=base_currency)

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    latest_exchange_rates = {
        exchange_rates.base_currency: exchange_rates
        for exchange_rates in await exchange_rates_handler.fetch_latest_valid()
    }

    for base_currency, currency_rates in exchange_rates_per_currency.items():
        assert (
            f"Exchange rates for {base_currency} are not stored in the database or "
            "are no longer valid, adding the currency to the list to be fetched"
        ) in caplog.messages
        assert f"Successfully fetched exchange rates for {base_currency}" in caplog.messages
        assert (
            f"Storing latest exchange rates for {base_currency} into the database"
            in caplog.messages
        )

        exchange_rates = latest_exchange_rates[base_currency]
        assert exchange_rates is not None
        assert exchange_rates.api_response["base_code"] == base_currency
        assert exchange_rates.api_response["conversion_rates"] == currency_rates

        assert exchange_rates.last_update == datetime.fromtimestamp(
            exchange_rates.api_response["time_last_update_unix"], UTC
        )
        assert exchange_rates.next_update == datetime.fromtimestamp(
            exchange_rates.api_response["time_next_update_unix"], UTC
        )


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_dont_fetch_exchange_rates_when_recent_are_present_in_db(
    organization_factory: ModelFactory[Organization],
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    exchange_rates_factory: ModelFactory[ExchangeRates],
    caplog: pytest.LogCaptureFixture,
):
    await organization_factory(currency="USD")
    await exchange_rates_factory(base_currency="USD")

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    assert (
        "Exchange rates for USD are already stored in the database and are still valid, "
        "skipping feching them" in caplog.messages
    )

    mock_exchange_rate_api_client.assert_no_api_calls()


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_fetch_exchange_rates_when_outdated_are_present_in_db(
    organization_factory: ModelFactory[Organization],
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    exchange_rates_factory: ModelFactory[ExchangeRates],
    caplog: pytest.LogCaptureFixture,
):
    await organization_factory(currency="USD")

    exchange_rates_handler = ExchangeRatesHandler(db_session)

    await exchange_rates_factory(
        base_currency="USD",
        last_update=datetime.now(UTC) - timedelta(days=1),
        next_update=datetime.now(UTC) - timedelta(minutes=1),
    )
    mock_exchange_rate_api_client.mock_get_latest_rates(
        base_currency="USD",
        exchange_rates={  # A happy day for Europe :)
            "USD": 1.0,
            "EUR": 0.200,
            "GBP": 0.100,
        },
    )

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    assert (
        "Exchange rates for USD are not stored in the database or are no longer valid, "
        "adding the currency to the list to be fetched"
    ) in caplog.messages
    assert "Fetching latest exchange rates for USD" in caplog.messages
    assert "Completed storing exchange rates for USD" in caplog.messages

    new_exchange_rates = await exchange_rates_handler.query_db()
    assert len(new_exchange_rates) == 2

    latest_exchange_rates = await exchange_rates_handler.fetch_latest_valid()

    assert len(latest_exchange_rates) == 1
    assert latest_exchange_rates[0].api_response["conversion_rates"] == {
        "USD": 1.0,
        "EUR": 0.200,
        "GBP": 0.100,
    }


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_exchange_rate_api_rerturns_unrecoverable_error(
    organization_factory: ModelFactory[Organization],
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    caplog: pytest.LogCaptureFixture,
):
    await organization_factory(currency="USD")
    exchange_rates_handler = ExchangeRatesHandler(db_session)

    mock_exchange_rate_api_client.mock_get_latest_rates(
        base_currency="USD", error_code=ExchangeRateAPIErrorType.INACTIVE_ACCOUNT
    )

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    assert "Fetching latest exchange rates for USD" in caplog.messages
    assert "Failed to fetch exchange rates for USD due to an exception" in caplog.messages

    log_with_exception = next(
        record for record in caplog.records if "Failed to fetch exchange rates" in record.message
    )
    assert log_with_exception.levelno == logging.ERROR
    assert log_with_exception.exc_info is not None
    exc_type, exc_value, traceback = log_with_exception.exc_info
    assert exc_type is ExchangeRateAPIError
    assert exc_value.error_type == ExchangeRateAPIErrorType.INACTIVE_ACCOUNT  # type: ignore[union-attr]
    assert traceback is not None

    assert not await exchange_rates_handler.query_db()


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_exchange_rate_api_timeouts_then_succeeds(
    organization_factory: ModelFactory[Organization],
    exchange_rates_per_currency: dict[str, dict[str, float]],
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    caplog: pytest.LogCaptureFixture,
):
    await organization_factory(currency="USD")
    exchange_rates_handler = ExchangeRatesHandler(db_session)

    mock_exchange_rate_api_client.simulate_read_timeout()
    mock_exchange_rate_api_client.mock_get_latest_rates(base_currency="USD")

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    latest_exchange_rates = await exchange_rates_handler.fetch_latest_valid()
    assert len(latest_exchange_rates) == 1

    assert (
        latest_exchange_rates[0].api_response["conversion_rates"]
        == exchange_rates_per_currency["USD"]
    )

    assert "Fetching latest exchange rates for USD" in caplog.messages
    assert "stamina.retry_scheduled" in caplog.messages
    assert "Successfully fetched exchange rates for USD" in caplog.messages

    stamina_log = next(
        record for record in caplog.records if "stamina.retry_scheduled" in record.message
    )
    stamina_log_extra = stamina_log.__dict__

    assert stamina_log_extra["stamina.caused_by"] == "ReadTimeout('Unable to read within timeout')"


def test_cli_command(
    mocker: MockerFixture,
    test_settings: Settings,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
):
    mocker.patch("app.cli.get_settings", return_value=test_settings)
    mock_command_coro = mocker.MagicMock()
    mock_command = mocker.MagicMock(return_value=mock_command_coro)

    mocker.patch("app.commands.update_latest_exchange_rates.main", mock_command)
    mock_run = mocker.patch("app.commands.update_latest_exchange_rates.asyncio.run")
    runner = CliRunner()

    result = runner.invoke(app, ["update-latest-exchange-rates"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(mock_command_coro)

    mock_exchange_rate_api_client.assert_no_api_calls()
