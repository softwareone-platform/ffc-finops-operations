import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import time_machine
from fastapi import status
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.commands import update_current_month_datasource_expenses
from app.conf import Settings
from app.db.handlers import DatasourceExpenseHandler
from app.db.models import DatasourceExpense, Organization
from app.enums import OrganizationStatus
from tests.fixtures.mock_api_clients import MockOptscaleClient
from tests.types import ModelFactory


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
@pytest.mark.parametrize(
    "organization_status",
    [
        OrganizationStatus.ACTIVE,
        OrganizationStatus.CANCELLED,
        OrganizationStatus.DELETED,
    ],
)
async def test_create_new_datasource_expenses_single_organization(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_optscale_client: MockOptscaleClient,
    organization_factory: ModelFactory[Organization],
    organization_status: OrganizationStatus,
):
    datasource_expense_handler = DatasourceExpenseHandler(db_session)
    organization = await organization_factory(
        linked_organization_id=str(uuid.uuid4()),
        status=organization_status,
    )

    datasource_id1 = str(uuid.uuid4())
    datasource_id2 = str(uuid.uuid4())

    mock_optscale_client.mock_fetch_datasources_for_organization(
        organization,
        [
            {"id": datasource_id1, "name": "First cloud account", "details": {"cost": 123.45}},
            {"id": datasource_id2, "name": "Second cloud account", "details": {"cost": 567.89}},
        ],
    )

    existing_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(existing_datasource_expenses) == 0

    await update_current_month_datasource_expenses.main(test_settings)

    new_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(new_datasource_expenses) == 2

    ds_exp1 = next(
        ds_exp for ds_exp in new_datasource_expenses if ds_exp.datasource_id == datasource_id1
    )
    ds_exp2 = next(
        ds_exp for ds_exp in new_datasource_expenses if ds_exp.datasource_id == datasource_id2
    )

    assert ds_exp1.organization_id == organization.id
    assert ds_exp1.year == 2025
    assert ds_exp1.month == 3
    assert ds_exp1.month_expenses == Decimal("123.45")
    assert ds_exp1.datasource_name == "First cloud account"

    assert ds_exp2.organization_id == organization.id
    assert ds_exp2.year == 2025
    assert ds_exp2.month == 3
    assert ds_exp2.month_expenses == Decimal("567.89")
    assert ds_exp2.datasource_name == "Second cloud account"


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_datasource_expenses_are_updated_for_current_month(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_optscale_client: MockOptscaleClient,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
):
    datasource_expense_handler = DatasourceExpenseHandler(db_session)
    organization = await organization_factory(linked_organization_id=str(uuid.uuid4()))

    datasource_id1 = str(uuid.uuid4())
    datasource_id2 = str(uuid.uuid4())

    existing_datasource_expense1 = await datasource_expense_factory(
        organization=organization,
        datasource_id=datasource_id1,
        datasource_name="First cloud account",
        year=2025,
        month=3,  # NOTE: This is for the current month, so it should be updated
        month_expenses=Decimal("123.45"),
    )

    existing_datasource_expense2 = await datasource_expense_factory(
        organization=organization,
        datasource_id=datasource_id2,
        datasource_name="Second cloud account",
        year=2025,
        month=2,  # NOTE: this is for the previous month, so it should NOT be updated
        month_expenses=Decimal("567.89"),
    )

    mock_optscale_client.mock_fetch_datasources_for_organization(
        organization,
        [
            {"id": datasource_id1, "name": "First cloud account", "details": {"cost": 234.56}},
            {"id": datasource_id2, "name": "Second cloud account", "details": {"cost": 678.90}},
        ],
    )

    existing_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(existing_datasource_expenses) == 2

    await update_current_month_datasource_expenses.main(test_settings)

    new_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(new_datasource_expenses) == 3

    ds_exp1 = next(
        ds_exp for ds_exp in new_datasource_expenses if ds_exp.datasource_id == datasource_id1
    )
    ds_exp2_current_month = next(
        ds_exp
        for ds_exp in new_datasource_expenses
        if (ds_exp.datasource_id == datasource_id2 and ds_exp.month == 2)
    )

    ds_exp2_this_month = next(
        ds_exp
        for ds_exp in new_datasource_expenses
        if (ds_exp.datasource_id == datasource_id2 and ds_exp.month == 3)
    )

    await db_session.refresh(existing_datasource_expense1)

    assert ds_exp1.id == existing_datasource_expense1.id
    assert ds_exp1.datasource_name == "First cloud account"
    assert ds_exp1.organization_id == organization.id
    assert ds_exp1.year == 2025
    assert ds_exp1.month == 3
    assert ds_exp1.month_expenses == Decimal("234.56")

    assert ds_exp2_current_month.id == existing_datasource_expense2.id
    assert ds_exp2_current_month.datasource_name == "Second cloud account"
    assert ds_exp2_current_month.organization_id == organization.id
    assert ds_exp2_current_month.year == 2025
    assert ds_exp2_current_month.month == 2
    assert ds_exp2_current_month.month_expenses == Decimal("567.89")

    assert ds_exp2_this_month.id not in (
        existing_datasource_expense1.id,
        existing_datasource_expense2.id,
    )
    assert ds_exp2_this_month.datasource_name == "Second cloud account"
    assert ds_exp2_this_month.organization_id == organization.id
    assert ds_exp2_this_month.year == 2025
    assert ds_exp2_this_month.month == 3
    assert ds_exp2_this_month.month_expenses == Decimal("678.90")


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_organization_with_no_linked_organization_id(
    test_settings: Settings,
    db_session: AsyncSession,
    organization_factory: ModelFactory[Organization],
    caplog: pytest.LogCaptureFixture,
    httpx_mock: HTTPXMock,
):
    datasource_expense_handler = DatasourceExpenseHandler(db_session)
    organization = await organization_factory(linked_organization_id=None)

    with caplog.at_level(logging.WARNING):
        await update_current_month_datasource_expenses.main(test_settings)

    assert (
        f"Organization {organization.id} has no linked organization ID. Skipping..." in caplog.text
    )

    new_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(new_datasource_expenses) == 0

    assert not httpx_mock.get_request()


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_organization_with_recent_updates_to_datasource_expences(
    test_settings: Settings,
    db_session: AsyncSession,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    httpx_mock: HTTPXMock,
    mocker: MockerFixture,
):
    organization = await organization_factory(linked_organization_id=None)

    store_datasource_expenses_mock = mocker.patch(
        "app.commands.update_current_month_datasource_expenses.store_datasource_expenses"
    )

    await datasource_expense_factory(
        organization=organization,
        year=2025,
        month=3,
        month_expenses=Decimal("123.45"),
        updated_at=datetime.now(UTC),
    )

    await update_current_month_datasource_expenses.main(test_settings)
    assert not httpx_mock.get_request()
    store_datasource_expenses_mock.assert_called_once_with(mocker.ANY, {}, year=2025, month=3)


@pytest.mark.parametrize(
    ("status_code", "expected_log_level", "expected_log_format"),
    [
        (
            status.HTTP_404_NOT_FOUND,
            logging.WARNING,
            "Organization %s not found on Optscale. Skipping...",
        ),
        (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            logging.ERROR,
            "Unexpected error occurred fetching datasources for organization %s",
        ),
    ],
)
@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_optscale_api_returns_exception(
    test_settings: Settings,
    db_session: AsyncSession,
    organization_factory: ModelFactory[Organization],
    caplog: pytest.LogCaptureFixture,
    mock_optscale_client: MockOptscaleClient,
    status_code: int,
    expected_log_level: int,
    expected_log_format: str,
):
    datasource_expense_handler = DatasourceExpenseHandler(db_session)
    organization = await organization_factory(linked_organization_id=str(uuid.uuid4()))

    mock_optscale_client.mock_fetch_datasources_for_organization(
        organization, status_code=status_code
    )

    with caplog.at_level(logging.WARNING):
        await update_current_month_datasource_expenses.main(test_settings)

    assert (
        update_current_month_datasource_expenses.logger.name,
        expected_log_level,
        expected_log_format % organization.id,
    ) in caplog.record_tuples

    new_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(new_datasource_expenses) == 0


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_multiple_datasources_are_handled_correctly(
    test_settings: Settings,
    db_session: AsyncSession,
    mock_optscale_client: MockOptscaleClient,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    caplog: pytest.LogCaptureFixture,
):
    datasource_expense_handler = DatasourceExpenseHandler(db_session)
    organization1 = await organization_factory(
        linked_organization_id=str(uuid.uuid4()), operations_external_id="org_1_external_id"
    )
    organization2 = await organization_factory(
        linked_organization_id=str(uuid.uuid4()), operations_external_id="org_2_external_id"
    )
    organization3 = await organization_factory(
        linked_organization_id=str(uuid.uuid4()), operations_external_id="org_3_external_id"
    )
    organization4 = await organization_factory(
        linked_organization_id=str(uuid.uuid4()), operations_external_id="org_4_external_id"
    )

    org_1_datasource_id1 = str(uuid.uuid4())
    org_1_datasource_id2 = str(uuid.uuid4())
    org_1_datasource_id3 = str(uuid.uuid4())
    org_1_datasource_id4 = str(uuid.uuid4())

    org_2_datasource_id1 = str(uuid.uuid4())
    org_2_datasource_id2 = str(uuid.uuid4())

    org_3_datasource_id1 = str(uuid.uuid4())

    await datasource_expense_factory(
        organization=organization1,
        datasource_id=org_1_datasource_id1,
        year=2025,
        month=2,
        month_expenses=Decimal("123.45"),
    )

    await datasource_expense_factory(
        organization=organization1,
        datasource_id=org_1_datasource_id1,
        year=2025,
        month=3,
        month_expenses=Decimal("234.56"),
    )

    await datasource_expense_factory(
        organization=organization1,
        datasource_id=org_1_datasource_id2,
        year=2025,
        month=3,
        month_expenses=Decimal("567.89"),
    )

    await datasource_expense_factory(
        organization=organization2,
        datasource_id=org_2_datasource_id1,
        year=2025,
        month=3,
        month_expenses=Decimal("999.88"),
    )

    existing_datasource_expenses = await datasource_expense_handler.query_db(unique=True)
    assert len(existing_datasource_expenses) == 4

    mock_optscale_client.mock_fetch_datasources_for_organization(
        organization1,
        [
            {"id": org_1_datasource_id1, "details": {"cost": 789.01}},
            {"id": org_1_datasource_id2, "details": {"cost": 678.90}},
            {"id": org_1_datasource_id3, "type": "azure_tenant"},
            {"id": org_1_datasource_id4, "type": "gcp_tenant"},
        ],
    )

    mock_optscale_client.mock_fetch_datasources_for_organization(
        organization2,
        [
            {"id": org_2_datasource_id1, "details": {"cost": 234.56}},
            {"id": org_2_datasource_id2, "details": {"cost": 654.32}},
        ],
    )

    mock_optscale_client.mock_fetch_datasources_for_organization(
        organization3,
        [{"id": org_3_datasource_id1, "details": {"cost": 777.88}}],
    )

    mock_optscale_client.mock_fetch_datasources_for_organization(organization4, status_code=404)

    with caplog.at_level(logging.WARNING):
        await update_current_month_datasource_expenses.main(test_settings)
        assert (
            f"Skipping child datasource {org_1_datasource_id3} of type azure_tenant" in caplog.text
        )
        assert f"Skipping child datasource {org_1_datasource_id4} of type gcp_tenant" in caplog.text
        assert f"Organization {organization4.id} not found on Optscale. Skipping..." in caplog.text

    new_datasource_expenses = await datasource_expense_handler.query_db(unique=True)

    expenses_data = {
        (
            ds_exp.organization_id,
            ds_exp.datasource_id,
            ds_exp.year,
            ds_exp.month,
            ds_exp.month_expenses,
        )
        for ds_exp in new_datasource_expenses
    }

    assert expenses_data == {
        (organization1.id, org_1_datasource_id1, 2025, 2, Decimal("123.4500")),
        (organization1.id, org_1_datasource_id1, 2025, 3, Decimal("234.5600")),
        (organization1.id, org_1_datasource_id2, 2025, 3, Decimal("567.8900")),
        (organization2.id, org_2_datasource_id1, 2025, 3, Decimal("999.8800")),
        (organization2.id, org_2_datasource_id2, 2025, 3, Decimal("654.3200")),
        (organization3.id, org_3_datasource_id1, 2025, 3, Decimal("777.8800")),
    }


def test_cli_command(mocker: MockerFixture, test_settings: Settings):
    mocker.patch("app.cli.get_settings", return_value=test_settings)
    mock_command_coro = mocker.MagicMock()
    mock_command = mocker.MagicMock(return_value=mock_command_coro)

    mocker.patch("app.commands.update_current_month_datasource_expenses.main", mock_command)
    mock_run = mocker.patch("app.commands.update_current_month_datasource_expenses.asyncio.run")
    runner = CliRunner()

    result = runner.invoke(app, ["update-current-month-datasource-expenses"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(mock_command_coro)
