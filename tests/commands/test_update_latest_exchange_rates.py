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
from app.db.models import ExchangeRates
from tests.fixtures.mock_api_clients import MockExchangeRateAPIClient
from tests.types import ModelFactory


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_successful_fetch_exchange_rates_when_missing(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    time_machine: time_machine.TimeMachineFixture,
    caplog: pytest.LogCaptureFixture,
):
    exchange_rates_handler = ExchangeRatesHandler(db_session)

    existing_exchange_rates = await exchange_rates_handler.query_db()
    assert len(existing_exchange_rates) == 0
    mock_exchange_rate_api_client.mock_get_latest_rates(
        base_currency="USD",
        exchange_rates={
            "USD": 1.0,
            "EUR": 0.9252,
            "GBP": 0.7737,
        },
    )

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    assert caplog.messages == [
        "Exchange rates are not stored in the database or are no longer valid",
        "Fetching latest exchange rates against USD",
        "Successfully fetched exchange rates",
        "Storing latest exchange rates into the database",
        "Completed storing exchange rates",
    ]

    new_exchange_rates = await exchange_rates_handler.query_db()
    assert len(new_exchange_rates) == 1

    exchange_rates = new_exchange_rates[0]

    assert exchange_rates.api_response["base_code"] == "USD"
    assert exchange_rates.api_response["conversion_rates"] == {
        "USD": 1.0,
        "EUR": 0.9252,
        "GBP": 0.7737,
    }

    assert exchange_rates.base_currency == exchange_rates.api_response["base_code"]
    assert exchange_rates.last_update == datetime.fromtimestamp(
        exchange_rates.api_response["time_last_update_unix"], UTC
    )
    assert exchange_rates.next_update == datetime.fromtimestamp(
        exchange_rates.api_response["time_next_update_unix"], UTC
    )


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_dont_fetch_exchange_rates_when_recent_are_present_in_db(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    exchange_rates_factory: ModelFactory[ExchangeRates],
    caplog: pytest.LogCaptureFixture,
):
    await exchange_rates_factory()

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    assert caplog.messages == [
        "Exchange rates are already stored in the database and are still valid",
        "Skipping fetching exchange rates",
    ]

    mock_exchange_rate_api_client.assert_no_api_calls()


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_fetch_exchange_rates_when_outdated_are_present_in_db(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    exchange_rates_factory: ModelFactory[ExchangeRates],
    caplog: pytest.LogCaptureFixture,
):
    exchange_rates_handler = ExchangeRatesHandler(db_session)

    await exchange_rates_factory(
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

    assert caplog.messages == [
        "Exchange rates are not stored in the database or are no longer valid",
        "Fetching latest exchange rates against USD",
        "Successfully fetched exchange rates",
        "Storing latest exchange rates into the database",
        "Completed storing exchange rates",
    ]

    new_exchange_rates = await exchange_rates_handler.query_db()
    assert len(new_exchange_rates) == 2

    latest_exchange_rates = await exchange_rates_handler.fetch_latest_valid()

    assert latest_exchange_rates is not None
    assert latest_exchange_rates.api_response["conversion_rates"] == {
        "USD": 1.0,
        "EUR": 0.200,
        "GBP": 0.100,
    }


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_exchange_rate_api_rerturns_unrecoverable_error(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    caplog: pytest.LogCaptureFixture,
):
    exchange_rates_handler = ExchangeRatesHandler(db_session)

    mock_exchange_rate_api_client.mock_get_latest_rates(
        error_code=ExchangeRateAPIErrorType.INACTIVE_ACCOUNT
    )

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        with pytest.raises(ExchangeRateAPIError) as exc_info:
            await update_latest_exchange_rates.main(test_settings)

    assert exc_info.value.error_type == ExchangeRateAPIErrorType.INACTIVE_ACCOUNT

    assert caplog.messages == [
        "Exchange rates are not stored in the database or are no longer valid",
        "Fetching latest exchange rates against USD",
        "Failed to fetch exchange rates due to an exception",
    ]

    assert caplog.records[-1].exc_info is not None

    assert not await exchange_rates_handler.query_db()


@time_machine.travel("2025-03-26T10:00:00Z", tick=False)
async def test_exchange_rate_api_timeouts_then_succeeds(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_exchange_rate_api_client: MockExchangeRateAPIClient,
    caplog: pytest.LogCaptureFixture,
):
    exchange_rates_handler = ExchangeRatesHandler(db_session)

    mock_exchange_rate_api_client.simulate_read_timeout()
    mock_exchange_rate_api_client.mock_get_latest_rates(
        base_currency="USD",
        exchange_rates={
            "USD": 1.0,
            "EUR": 0.9252,
            "GBP": 0.7737,
        },
    )

    with caplog.at_level(logging.INFO, logger="app.commands.update_latest_exchange_rates"):
        await update_latest_exchange_rates.main(test_settings)

    latest_exchange_rates = await exchange_rates_handler.fetch_latest_valid()

    assert latest_exchange_rates is not None
    assert latest_exchange_rates.api_response["conversion_rates"] == {
        "USD": 1.0,
        "EUR": 0.9252,
        "GBP": 0.7737,
    }

    assert caplog.messages == [
        "Exchange rates are not stored in the database or are no longer valid",
        "Fetching latest exchange rates against USD",
        "stamina.retry_scheduled",
        "Successfully fetched exchange rates",
        "Storing latest exchange rates into the database",
        "Completed storing exchange rates",
    ]

    stamina_log = caplog.records[2]
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
