import io
import logging
import pathlib
import tempfile
import zipfile
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest
import time_machine
from azure.core.exceptions import AzureError, ClientAuthenticationError, ResourceNotFoundError
from faker import Faker
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.commands.generate_monthly_charges import (
    ChargeEntry,
    ChargesFileGenerator,
    fetch_accounts,
    fetch_datasource_expenses,
    fetch_existing_generated_charges_file,
    fetch_unique_billing_currencies,
    upload_charges_file_to_azure,
)
from app.commands.generate_monthly_charges import main as generate_monthly_charges_main
from app.conf import Settings
from app.currency import CurrencyConverter
from app.db.handlers import ChargesFileHandler
from app.db.models import (
    Account,
    ChargesFile,
    DatasourceExpense,
    Entitlement,
    ExchangeRates,
    Organization,
)
from app.enums import (
    AccountStatus,
    AccountType,
    ChargesFileStatus,
    DatasourceType,
    EntitlementStatus,
    OrganizationStatus,
)
from tests.conftest import ModelFactory


@pytest.fixture
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def currency_converter(
    db_session: AsyncSession,
    exchange_rates_factory: ModelFactory[ExchangeRates],
) -> CurrencyConverter:
    await exchange_rates_factory(base_currency="USD")
    await exchange_rates_factory(base_currency="GBP")
    await exchange_rates_factory(base_currency="EUR")

    return await CurrencyConverter.from_db(db_session)


@pytest.fixture
async def another_affiliate_account(account_factory: ModelFactory[Account]):
    return await account_factory(type=AccountType.AFFILIATE)


@pytest.fixture
async def usd_org_billed_in_eur_expenses(
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    affiliate_account: Account,
    another_affiliate_account: Account,
    db_session: AsyncSession,
    faker: Faker,
):
    org = await organization_factory(
        operations_external_id="ORG-12345",
        name=faker.company(),
        currency="USD",
        billing_currency="EUR",
        status=OrganizationStatus.ACTIVE,
        linked_organization_id=faker.uuid4(str),
    )
    aws_acc_feb_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="11111111111",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="AWS Account",
        organization=org,
        month=2,
        year=2025,
        day=1,
        expenses=Decimal("50.00"),
        created_at=datetime(2025, 2, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 2, 28, 10, 0, 0, tzinfo=UTC),
    )
    aws_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id=aws_acc_feb_expenses.datasource_id,
        linked_datasource_id=aws_acc_feb_expenses.linked_datasource_id,
        linked_datasource_type=aws_acc_feb_expenses.linked_datasource_type,
        datasource_name=aws_acc_feb_expenses.datasource_name,
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("60.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )
    gcp_acc_mar_expenses = await datasource_expense_factory(
        datasource_id="22222222222",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.GCP_CNR,
        datasource_name="GCP Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("70.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="free GCP account",
        affiliate_external_id="ACC-11111",
        datasource_id=gcp_acc_mar_expenses.datasource_id,
        linked_datasource_id=gcp_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=gcp_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    # Should be ignored
    await entitlement_factory(
        name="free AWS account",
        affiliate_external_id="ACC-22222",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        # Intentionally set to None to verify that the relationship
        # with the datasource expense is still happening
        linked_datasource_id=None,
        linked_datasource_type=DatasourceType.AWS_CNR,
        status=EntitlementStatus.ACTIVE,
        owner=another_affiliate_account,
    )

    # Load the entitlement relationships on the datasource expense model
    await db_session.refresh(aws_acc_mar_expenses)
    await db_session.refresh(gcp_acc_mar_expenses)

    return org


@pytest.fixture
async def eur_org_billed_in_gbp_expenses(
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    affiliate_account: Account,
    db_session: AsyncSession,
    faker: Faker,
):
    org = await organization_factory(
        operations_external_id="ORG-56789",
        name=faker.company(),
        currency="EUR",
        billing_currency="GBP",
        # doesn't matter that it's deleted, should be still included
        status=OrganizationStatus.DELETED,
        linked_organization_id=faker.uuid4(str),
    )

    aws_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="33333333333",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="AWS Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("50.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    azure_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="44444444444",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AZURE_CNR,
        datasource_name="Azure Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("40.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="Free AWS account",
        affiliate_external_id="ACC-33333",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        linked_datasource_id=aws_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=aws_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.TERMINATED,  # should be ignored
        owner=affiliate_account,
    )

    await entitlement_factory(
        name="Free Azure account",
        affiliate_external_id="ACC-44444",
        datasource_id=azure_acc_mar_expenses.datasource_id,
        linked_datasource_id=azure_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=azure_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    await db_session.refresh(aws_acc_mar_expenses)
    await db_session.refresh(azure_acc_mar_expenses)

    return org


@pytest.fixture
async def gbp_org_billed_in_eur_expenses(
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    affiliate_account: Account,
    db_session: AsyncSession,
    faker: Faker,
):
    org = await organization_factory(
        operations_external_id="ORG-22222",
        name=faker.company(),
        currency="GBP",
        billing_currency="EUR",
        status=OrganizationStatus.ACTIVE,
        linked_organization_id=faker.uuid4(str),
    )

    aws_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="55555555555",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="AWS Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("50.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    azure_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="66666666666",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AZURE_CNR,
        datasource_name="Azure Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("40.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="Free AWS account",
        affiliate_external_id="ACC-111111",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        linked_datasource_id=aws_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=aws_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.TERMINATED,  # should be ignored
        owner=affiliate_account,
    )

    await entitlement_factory(
        name="Free Azure account",
        affiliate_external_id="ACC-888888",
        datasource_id=azure_acc_mar_expenses.datasource_id,
        linked_datasource_id=azure_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=azure_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    await db_session.refresh(aws_acc_mar_expenses)
    await db_session.refresh(azure_acc_mar_expenses)

    return org


@pytest.fixture
async def eur_org_billed_in_eur_expenses(
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    affiliate_account: Account,
    db_session: AsyncSession,
    faker: Faker,
):
    org = await organization_factory(
        operations_external_id="ORG-77777",
        name=faker.company(),
        currency="EUR",
        billing_currency="EUR",
        status=OrganizationStatus.ACTIVE,
        linked_organization_id=faker.uuid4(str),
    )

    aws_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="77777777777",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="AWS Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("50.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    azure_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="88888888888",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AZURE_CNR,
        datasource_name="Azure Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("40.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="Free AWS account",
        affiliate_external_id="ACC-99999",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        linked_datasource_id=aws_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=aws_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.TERMINATED,  # should be ignored
        owner=affiliate_account,
    )

    await entitlement_factory(
        name="Free Azure account",
        affiliate_external_id="ACC-88888",
        datasource_id=azure_acc_mar_expenses.datasource_id,
        linked_datasource_id=azure_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=azure_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    await db_session.refresh(aws_acc_mar_expenses)
    await db_session.refresh(azure_acc_mar_expenses)

    return org


@pytest.fixture
async def usd_org_billed_in_usd_expenses(
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    affiliate_account: Account,
    db_session: AsyncSession,
    faker: Faker,
):
    org = await organization_factory(
        operations_external_id="ORG-98765",
        name=faker.company(),
        currency="USD",
        billing_currency="USD",
        status=OrganizationStatus.ACTIVE,
        linked_organization_id=faker.uuid4(str),
    )
    aws_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="99999999999",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="AWS Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("60.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )
    gcp_acc_mar_expenses = await datasource_expense_factory(
        datasource_id="00000000000",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.GCP_CNR,
        datasource_name="GCP Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("70.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )
    azure_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id="10101010101",
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AZURE_CNR,
        datasource_name="Azure Account",
        organization=org,
        month=3,
        year=2025,
        day=1,
        expenses=Decimal("40.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="free AWS account",
        affiliate_external_id="ACC-55555",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        linked_datasource_id=aws_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=aws_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    # Should be ignored
    await entitlement_factory(
        name="free GCP account",
        affiliate_external_id="ACC-66666",
        datasource_id=gcp_acc_mar_expenses.datasource_id,
        linked_datasource_id=gcp_acc_mar_expenses.linked_datasource_id,
        linked_datasource_type=gcp_acc_mar_expenses.linked_datasource_type,
        status=EntitlementStatus.TERMINATED,
        owner=affiliate_account,
    )


def assert_generated_file_matches_snapshot(
    excel_file_path: pathlib.Path,
    snapshot: Snapshot,
) -> None:
    # We're exporting the data to CSV format, so that we can save it in a snapshot file.
    # We're intentionally using CSV instead of Excel format, as .xlsx is a binary format and
    # should the test fail, the diff would be unreadable and won't be obvious what's wrong.
    # Since we're still parsing the file from xlsx that is enough to guarantee that the file
    # is a valid xlsx file

    csv_file = io.StringIO()
    df = pd.read_excel(excel_file_path)
    df.to_csv(csv_file, index=False, header=True, float_format="%.2f")

    csv_file.seek(0)
    snapshot.assert_match(csv_file.read(), "charges.csv")


@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
def test_charges_file_generator_append_row(
    currency_converter: CurrencyConverter,
    operations_account: Account,
    test_settings: Settings,
    request: pytest.FixtureRequest,
    tmp_path: pathlib.Path,
):
    generator = ChargesFileGenerator(operations_account, "USD", currency_converter, tmp_path)

    # Since we're not saving to a file in this test, we need to close the temporary file
    # openpyxl creates explicitly when we're done with writing to it to avoid a warning
    # in the pytest output.
    request.addfinalizer(generator.worksheet.close)

    assert not generator.has_entries
    assert generator.total_rows == 0
    assert generator.running_total == Decimal("0.00")

    generator.append_row(
        ChargeEntry(
            subscription_search_criteria="subscription.externalIds.vendor",
            subscription_search_value=operations_account.id,
            item_search_criteria="item.externalIds.vendor",
            item_search_value=test_settings.ffc_external_product_id,
            usage_start_time=(datetime.now(UTC) - timedelta(days=28)).date(),
            usage_end_time=datetime.now(UTC).date(),
            price=Decimal("1.00"),
            external_reference="ORG-1234-5678",
            vendor_description_1="AWS Account",
            vendor_description_2="123456789",
            vendor_reference="",
        )
    )

    assert generator.has_entries
    assert generator.total_rows == 2  # with the header
    assert generator.running_total == Decimal("1.00")

    generator.append_row(
        ChargeEntry(
            subscription_search_criteria="subscription.externalIds.vendor",
            subscription_search_value=operations_account.id,
            item_search_criteria="item.externalIds.vendor",
            item_search_value=test_settings.ffc_external_product_id,
            usage_start_time=(datetime.now(UTC) - timedelta(days=28)).date(),
            usage_end_time=datetime.now(UTC).date(),
            price=Decimal("2.00"),
            external_reference="ORG-1234-5678",
            vendor_description_1="GCP Account",
            vendor_description_2="987654321",
            vendor_reference="",
        )
    )

    assert generator.has_entries
    assert generator.total_rows == 3  # with the header
    assert generator.running_total == Decimal("3.00")


@pytest.mark.parametrize(
    ("account_fixture", "currency", "expected_total_rows", "expected_running_total"),
    [
        ("operations_account", "EUR", 5, Decimal("0.00")),
        ("affiliate_account", "EUR", 2, Decimal("0.65")),
        ("another_affiliate_account", "EUR", 2, Decimal("0.56")),
        ("operations_account", "GBP", 4, Decimal("0.43")),
        ("affiliate_account", "GBP", 2, Decimal("0.34")),
        ("another_affiliate_account", "GBP", 0, Decimal("0.00")),
        ("operations_account", "USD", 5, Decimal("1.10")),
        ("affiliate_account", "USD", 2, Decimal("0.60")),
        ("another_affiliate_account", "USD", 0, Decimal("0.00")),
    ],
)
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_charges_file_generator_add_datasource_expense(
    currency_converter: CurrencyConverter,
    usd_org_billed_in_usd_expenses: Organization,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_gbp_expenses: Organization,
    db_session: AsyncSession,
    request: pytest.FixtureRequest,
    tmp_path: pathlib.Path,
    account_fixture: str,
    currency: str,
    expected_total_rows: int,
    expected_running_total: Decimal,
):
    account = request.getfixturevalue(account_fixture)

    generator = ChargesFileGenerator(account, currency, currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, currency):
        generator.add_datasource_expense(ds_exp)

    generator.save("charges.xlsx")
    assert generator.has_entries == (generator.total_rows > 0)
    assert generator.total_rows == expected_total_rows  # with the header
    assert generator.running_total.quantize(Decimal("0.00")) == expected_running_total


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_charges_file_dataframe_operations_same_currency(
    currency_converter: CurrencyConverter,
    operations_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    snapshot: Snapshot,
    db_session: AsyncSession,
    tmp_path: pathlib.Path,
):
    generator = ChargesFileGenerator(operations_account, "USD", currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, "USD"):
        generator.add_datasource_expense(ds_exp)

    assert_generated_file_matches_snapshot(generator.save("charges.xlsx"), snapshot)


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_charges_file_dataframe_affiliate_same_currency(
    currency_converter: CurrencyConverter,
    affiliate_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    db_session: AsyncSession,
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
):
    generator = ChargesFileGenerator(affiliate_account, "USD", currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, "USD"):
        generator.add_datasource_expense(ds_exp)

    assert_generated_file_matches_snapshot(generator.save("charges.xlsx"), snapshot)


async def test_generate_charges_file_dataframe_empty_file(
    currency_converter: CurrencyConverter,
    usd_org_billed_in_usd_expenses: Organization,
    affiliate_account: Account,
    db_session: AsyncSession,
    tmp_path: pathlib.Path,
):
    generator = ChargesFileGenerator(affiliate_account, "EUR", currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, "EUR"):
        generator.add_datasource_expense(ds_exp)

    assert not generator.has_entries


@pytest.mark.parametrize(
    "currency",
    ["USD", "EUR", "GBP"],
)
@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_charges_file_dataframe_affiliate_multiple_organizations_and_currencies(
    currency_converter: CurrencyConverter,
    affiliate_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_gbp_expenses: Organization,
    db_session: AsyncSession,
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
    currency: str,
):
    generator = ChargesFileGenerator(affiliate_account, currency, currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, currency):
        generator.add_datasource_expense(ds_exp)

    assert_generated_file_matches_snapshot(generator.save("charges.xlsx"), snapshot)


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_export_to_zip(
    exchange_rates_factory: ModelFactory[ExchangeRates],
    operations_account: Account,
    usd_org_billed_in_eur_expenses: Organization,
    currency_converter: CurrencyConverter,
    db_session: AsyncSession,
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
):
    generator = ChargesFileGenerator(operations_account, "EUR", currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, "EUR"):
        generator.add_datasource_expense(ds_exp)

    assert generator.has_entries

    zip_file_path = generator.make_archive("charges.zip")

    with zipfile.ZipFile(zip_file_path, "r") as archive:
        assert sorted(archive.namelist()) == ["charges.xlsx", "exchange_rates_USD.json"]

        excel_file_path = pathlib.Path(archive.extract("charges.xlsx", tmp_path))
        assert_generated_file_matches_snapshot(excel_file_path, snapshot)
        snapshot.assert_match(archive.read("exchange_rates_USD.json"), "exchange_rates.json")


@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_export_to_zip_includes_multiple_exchange_rates(
    exchange_rates_factory: ModelFactory[ExchangeRates],
    operations_account: Account,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_eur_expenses: Organization,
    gbp_org_billed_in_eur_expenses: Organization,
    currency_converter: CurrencyConverter,
    db_session: AsyncSession,
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
):
    generator = ChargesFileGenerator(operations_account, "EUR", currency_converter, tmp_path)

    async for ds_exp in fetch_datasource_expenses(db_session, "EUR"):
        generator.add_datasource_expense(ds_exp)

    assert generator.has_entries

    zip_file_path = generator.make_archive("charges.zip")

    with zipfile.ZipFile(zip_file_path, "r") as archive:
        assert sorted(archive.namelist()) == [
            "charges.xlsx",
            "exchange_rates_GBP.json",
            "exchange_rates_USD.json",
        ]


@pytest.mark.parametrize(
    ("currency", "expected_total_amount"),
    [
        ("USD", Decimal("1.10")),
        ("EUR", Decimal("0.00")),
        ("GBP", Decimal("0.43")),
    ],
)
@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_get_total_amount(
    currency_converter: CurrencyConverter,
    operations_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_gbp_expenses: Organization,
    tmp_path: pathlib.Path,
    snapshot: Snapshot,
    db_session: AsyncSession,
    currency: str,
    expected_total_amount: Decimal,
):
    generator = ChargesFileGenerator(operations_account, currency, currency_converter, tmp_path)
    async for ds_exp in fetch_datasource_expenses(db_session, currency):
        generator.add_datasource_expense(ds_exp)

    assert generator.has_entries

    df = pd.read_excel(generator.save("charges.xlsx"))

    total_amount = generator.running_total.quantize(Decimal("0.00"))
    assert total_amount == expected_total_amount
    assert total_amount == Decimal(df["Purchase Price"].sum()).quantize(Decimal("0.00"))
    assert total_amount == Decimal(df["Total Purchase Price"].sum()).quantize(Decimal("0.00"))


@pytest.mark.parametrize(
    ("side_effect", "should_upload", "should_raise"),
    [
        (None, True, False),
        (OSError("File is not readable"), False, False),
        (FileNotFoundError("File not found"), False, False),
        (ResourceNotFoundError("Azure resource not found"), True, True),
        (AzureError("Azure is down, what a surprise!"), True, True),
        (ClientAuthenticationError("Invalid credentials"), True, True),
    ],
)
async def test_upload_charges_file_to_azure(
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
    tmp_path: pathlib.Path,
    mocker: MockerFixture,
    side_effect: Exception | None,
    should_upload: bool,
    should_raise: bool,
):
    mocker.patch(
        "app.commands.generate_monthly_charges.upload_charges_file",
        side_effect=side_effect,
        return_value=should_upload,
    )

    charges_file = await charges_file_factory(
        currency="USD",
        owner=operations_account,
        status=ChargesFileStatus.DRAFT,
        document_date="2025-04-10",
    )

    file_to_be_uploaded = tmp_path / "dummy_file.zip"
    file_to_be_uploaded.touch()

    if should_raise:
        assert isinstance(side_effect, Exception)

        with pytest.raises(side_effect.__class__, match=str(side_effect)):
            await upload_charges_file_to_azure(charges_file, file_to_be_uploaded)
    else:
        result = await upload_charges_file_to_azure(charges_file, file_to_be_uploaded)
        assert result == should_upload


@pytest.mark.parametrize(
    ("existing_file_date", "existing_file_currency", "existing_file_status", "should_match"),
    [
        ("2025-04-10", "USD", ChargesFileStatus.GENERATED, True),
        ("2025-03-31", "USD", ChargesFileStatus.GENERATED, False),
        ("2025-04-01", "USD", ChargesFileStatus.PROCESSED, True),
        ("2025-04-01", "EUR", ChargesFileStatus.PROCESSED, False),
        ("2025-04-01", "USD", ChargesFileStatus.DELETED, False),
        ("2025-04-10", "USD", ChargesFileStatus.DRAFT, False),
    ],
)
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_fetch_existing_generated_charges_file(
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
    db_session: AsyncSession,
    existing_file_date: str,
    existing_file_currency: str,
    existing_file_status: ChargesFileStatus,
    should_match: bool,
):
    charges_file = await charges_file_factory(
        currency=existing_file_currency,
        owner=operations_account,
        status=existing_file_status,
        document_date=existing_file_date,
    )

    returned_charges_file = await fetch_existing_generated_charges_file(
        db_session, operations_account, "USD"
    )

    if should_match:
        assert returned_charges_file is not None
        assert charges_file.id == returned_charges_file.id
    else:
        assert returned_charges_file is None


@pytest.mark.parametrize(
    ("billing_currency", "expected_price"),
    [
        ("USD", Decimal("1.00")),
        ("EUR", Decimal("0.9252")),
        ("GBP", Decimal("0.7737")),
    ],
)
async def test_charge_entry_from_datasource_expense(
    currency_converter: CurrencyConverter,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    test_settings: Settings,
    billing_currency: str,
    expected_price: Decimal,
):
    organization = await organization_factory(
        operations_external_id="org1",
        name="Organization 1",
        status=OrganizationStatus.ACTIVE,
        currency="USD",
        billing_currency=billing_currency,
        linked_organization_id="organization_id_1",
    )
    datasource_expense = await datasource_expense_factory(
        datasource_id="ds_id1",
        datasource_name="Datasource 1",
        organization=organization,
        month=2,
        year=2025,
        day=1,
        expenses=Decimal("100.00"),  # 100, so that it's easy to calculate
        created_at=datetime(2025, 2, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 2, 28, 10, 0, 0, tzinfo=UTC),
    )
    charge_entry = ChargeEntry.from_datasource_expense(datasource_expense, currency_converter)

    assert charge_entry.subscription_search_criteria == "subscription.externalIds.vendor"
    assert charge_entry.subscription_search_value == organization.id
    assert charge_entry.item_search_criteria == "item.externalIds.vendor"
    assert charge_entry.item_search_value == test_settings.ffc_external_product_id
    assert charge_entry.usage_start_time == date(2025, 2, 1)
    assert charge_entry.usage_end_time == date(2025, 2, 28)
    assert charge_entry.price == expected_price
    assert charge_entry.external_reference == organization.linked_organization_id
    assert charge_entry.vendor_description_1 == datasource_expense.datasource_name
    assert charge_entry.vendor_description_2 == datasource_expense.datasource_id
    assert charge_entry.vendor_reference == ""


async def test_charge_entry_from_datasource_expense_no_linked_organization_id(
    currency_converter: CurrencyConverter,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
):
    organization = await organization_factory(
        operations_external_id="org1",
        name="Organization 1",
        status=OrganizationStatus.ACTIVE,
        currency="USD",
        billing_currency="USD",
        linked_organization_id=None,
    )
    datasource_expense = await datasource_expense_factory(
        datasource_id="ds_id1",
        datasource_name="Datasource 1",
        organization=organization,
        month=2,
        year=2025,
        day=1,
        expenses=Decimal("100.00"),  # 100, so that it's easy to calculate
        created_at=datetime(2025, 2, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 2, 28, 10, 0, 0, tzinfo=UTC),
    )

    expected_error_message = (
        f"Cannot generate charge for datasource expense {datasource_expense.id}: "
        f"Organization {organization.id} does not have a linked organization ID."
    )

    with pytest.raises(ValueError) as exc_info:
        ChargeEntry.from_datasource_expense(datasource_expense, currency_converter)

    assert str(exc_info.value) == expected_error_message


async def test_fetch_unique_billing_currencies(
    organization_factory: ModelFactory[Organization],
    db_session: AsyncSession,
):
    await organization_factory(
        operations_external_id="org1",
        name="Organization 1",
        status=OrganizationStatus.ACTIVE,
        currency="USD",
        billing_currency="USD",
        linked_organization_id="organization_id_1",
    )

    await organization_factory(
        operations_external_id="org2",
        name="Organization 1",
        status=OrganizationStatus.DELETED,
        currency="USD",
        billing_currency="EUR",
        linked_organization_id="organization_id_2",
    )

    await organization_factory(
        operations_external_id="org3",
        name="Organization 3",
        status=OrganizationStatus.CANCELLED,
        currency="EUR",
        billing_currency="GBP",
        linked_organization_id=None,
    )

    currencies = await fetch_unique_billing_currencies(db_session)

    assert sorted(currencies) == ["EUR", "GBP", "USD"]


async def test_fetch_accounts(
    account_factory: ModelFactory[Account],
    db_session: AsyncSession,
):
    await account_factory(
        name="Operations Account",
        type=AccountType.OPERATIONS,
        status=AccountStatus.ACTIVE,
    )

    await account_factory(
        name="AWS Affiliate Account",
        type=AccountType.AFFILIATE,
        status=AccountStatus.ACTIVE,
    )

    await account_factory(
        name="GCP Affiliate Account",
        type=AccountType.AFFILIATE,
        status=AccountStatus.DELETED,
    )

    await account_factory(
        name="Azure Affiliate Account",
        type=AccountType.AFFILIATE,
        status=AccountStatus.DISABLED,
    )

    accounts = await fetch_accounts(db_session)

    account_names = sorted(account.name for account in accounts)

    assert account_names == [
        "AWS Affiliate Account",
        "Azure Affiliate Account",
        "GCP Affiliate Account",
        "Operations Account",
    ]


@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_full_run(
    exchange_rates_factory: ModelFactory[ExchangeRates],
    usd_org_billed_in_usd_expenses: Organization,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_gbp_expenses: Organization,
    charges_file_factory: ModelFactory[ChargesFile],
    affiliate_account: Account,
    another_affiliate_account: Account,
    operations_account: Account,
    gcp_account: Account,
    test_settings: Settings,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
):
    charges_file_handler = ChargesFileHandler(db_session)
    assert await charges_file_handler.count() == 0

    await exchange_rates_factory(base_currency="USD")
    await exchange_rates_factory(base_currency="EUR")
    await exchange_rates_factory(base_currency="GBP")

    # Add some existing charges files to the database to test that they are handled correctly

    # file is already generated, don't re-generate it
    generated_charges_file = await charges_file_factory(
        currency="EUR",
        owner=operations_account,
        status=ChargesFileStatus.GENERATED,
        document_date="2025-04-01",
    )

    # file is already processed, don't re-generate it
    processed_charges_file = await charges_file_factory(
        currency="EUR",
        owner=affiliate_account,
        status=ChargesFileStatus.PROCESSED,
        document_date="2025-04-01",
    )

    # file is already processed but it's old, shouldn't affect the run
    old_processed_charges_file = await charges_file_factory(
        currency="USD",
        owner=affiliate_account,
        status=ChargesFileStatus.PROCESSED,
        document_date="2025-03-01",
    )

    # file is deleted, should be re-generated with a new db record
    deleted_charges_file = await charges_file_factory(
        currency="USD",
        owner=operations_account,
        status=ChargesFileStatus.DELETED,
        document_date="2025-04-01",
    )

    # draft file, should be re-generated using the same db record
    draft_charges_file = await charges_file_factory(
        currency="GBP",
        owner=operations_account,
        status=ChargesFileStatus.DRAFT,
        document_date="2025-04-01",
    )

    time_before_run = datetime.now(UTC)

    # travel forward in time to set the updated_at date to all records affected by the main function
    # (both new records and updating existing ones), so that we can filter the affected records
    # bellow
    with caplog.at_level(logging.INFO), time_machine.travel("2025-04-10T11:00:00Z", tick=False):
        await generate_monthly_charges_main(exports_dir=tmp_path)

    await db_session.refresh(generated_charges_file)
    await db_session.refresh(processed_charges_file)
    await db_session.refresh(old_processed_charges_file)
    await db_session.refresh(deleted_charges_file)
    await db_session.refresh(draft_charges_file)

    # Includes new charges files created by the script as well as the ones which were updated by it
    updated_charges_files = (
        await db_session.scalars(
            select(ChargesFile).where(ChargesFile.updated_at > time_before_run)
        )
    ).all()

    assert generated_charges_file not in updated_charges_files
    assert processed_charges_file not in updated_charges_files
    assert old_processed_charges_file not in updated_charges_files
    assert deleted_charges_file not in updated_charges_files
    assert draft_charges_file in updated_charges_files

    generated_file_names = sorted(file.name for file in tmp_path.glob("*"))
    assert generated_file_names == sorted(
        f"{charges_file.id}.zip" for charges_file in updated_charges_files
    )

    azure_blobs = sorted(charge_file.azure_blob_name for charge_file in updated_charges_files)
    assert azure_blobs == sorted(
        f"{charges_file.currency}/{charges_file.document_date.year}/{charges_file.document_date.month:02}/{charges_file.id}.zip"
        for charges_file in updated_charges_files
    )

    assert all(
        charges_file.status == ChargesFileStatus.GENERATED for charges_file in updated_charges_files
    )

    # Confirm the statuses of the previously created charges files
    assert generated_charges_file.status == ChargesFileStatus.GENERATED
    assert processed_charges_file.status == ChargesFileStatus.PROCESSED
    assert old_processed_charges_file.status == ChargesFileStatus.PROCESSED
    assert deleted_charges_file.status == ChargesFileStatus.DELETED
    # this one was re-used, so its status has changed
    assert draft_charges_file.status == ChargesFileStatus.GENERATED

    charge_file_amounts = sorted(
        (cf.owner.id, cf.currency, cf.amount) for cf in updated_charges_files
    )
    assert charge_file_amounts == sorted(
        [
            (operations_account.id, "GBP", Decimal("0.4300")),
            (operations_account.id, "USD", Decimal("1.1000")),
            (affiliate_account.id, "GBP", Decimal("0.3400")),
            (affiliate_account.id, "USD", Decimal("0.6000")),
            (another_affiliate_account.id, "EUR", Decimal("0.5600")),
        ]
    )

    # filtering "Found ..." logs, so that tests failures are easier to debug
    found_logs = [msg for msg in caplog.messages if msg.startswith("Found ")]

    assert (
        "Found the following unique billing currencies from the database: EUR, GBP, USD"
        in found_logs
    )
    assert "Found 4 accounts in the database" in found_logs

    assert "Found 1 organizations to process with billing currency EUR" in found_logs
    assert "Found 1 organizations to process with billing currency GBP" in found_logs
    assert "Found 1 organizations to process with billing currency USD" in found_logs

    # filtering "Charges file ..." logs, so that tests failures are easier to debug
    charges_file_logs = [msg for msg in caplog.messages if msg.startswith("Charges file ")]

    assert (
        f"Charges file database record for account {operations_account.id} and currency GBP "
        f"already exists in DRAFT status: {draft_charges_file.id}, re-using it"
    ) in charges_file_logs

    assert (
        f"Charges file for account {operations_account.id} and currency EUR already exists "
        f"({generated_charges_file.id}) and it's in generated status, skipping generating a new one"
    ) in charges_file_logs

    assert (
        f"Charges file for account {affiliate_account.id} and currency EUR already exists "
        f"({processed_charges_file.id}) and it's in processed status, skipping generating a new one"
    ) in charges_file_logs

    newly_created_charges_file = next(
        cf
        for cf in updated_charges_files
        if cf.owner == deleted_charges_file.owner and cf.currency == deleted_charges_file.currency
    )
    assert (
        f"Charges file database record created for account {operations_account.id} "
        f"and currency USD in DRAFT status: {newly_created_charges_file.id}"
    ) in charges_file_logs
    assert newly_created_charges_file.id != deleted_charges_file.id


@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
@pytest.mark.parametrize(
    ("currency", "account_fixture_or_id", "expected_call_args", "exception"),
    [
        (
            None,
            None,
            [
                ("EUR", "operations_account"),
                ("EUR", "affiliate_account"),
                ("EUR", "another_affiliate_account"),
                ("GBP", "operations_account"),
                ("GBP", "affiliate_account"),
                ("GBP", "another_affiliate_account"),
                ("USD", "operations_account"),
                ("USD", "affiliate_account"),
                ("USD", "another_affiliate_account"),
            ],
            None,
        ),
        (
            "GBP",
            None,
            [
                ("GBP", "operations_account"),
                ("GBP", "affiliate_account"),
                ("GBP", "another_affiliate_account"),
            ],
            None,
        ),
        (
            None,
            "operations_account",
            [
                ("EUR", "operations_account"),
                ("GBP", "operations_account"),
                ("USD", "operations_account"),
            ],
            None,
        ),
        ("GBP", "operations_account", [("GBP", "operations_account")], None),
        (
            "CAD",
            None,
            [],
            ValueError(
                "Currency CAD is not used as a billing currency "
                "for any organization in the database"
            ),
        ),
        (
            None,
            "FACC-INVALID-ID",
            [],
            ValueError("Account FACC-INVALID-ID not found in the database"),
        ),
    ],
)
async def test_command_filters(
    exchange_rates_factory: ModelFactory[ExchangeRates],
    usd_org_billed_in_usd_expenses: Organization,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_gbp_expenses: Organization,
    affiliate_account: Account,
    another_affiliate_account: Account,
    operations_account: Account,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
    mocker: MockerFixture,
    request: pytest.FixtureRequest,
    currency: str | None,
    account_fixture_or_id: str | None,
    expected_call_args: list[tuple[str, str]],
    exception: Exception | None,
):
    mock_genenerate_monthly_charges = mocker.patch(
        "app.commands.generate_monthly_charges.genenerate_monthly_charges"
    )

    await exchange_rates_factory(base_currency="USD")
    await exchange_rates_factory(base_currency="EUR")
    await exchange_rates_factory(base_currency="GBP")

    if account_fixture_or_id is None:
        account_id = None
    elif account_fixture_or_id.startswith("FACC-"):
        account_id = account_fixture_or_id
    else:
        account_id = request.getfixturevalue(account_fixture_or_id).id

    with pytest.raises(exception.__class__, match=str(exception)) if exception else nullcontext():
        await generate_monthly_charges_main(
            exports_dir=tmp_path,
            account_id=account_id,
            currency=currency,
        )

    expected_calls_args = [
        (currency, request.getfixturevalue(account_fixture).id)
        for currency, account_fixture in expected_call_args
    ]

    actual_calls_args = [
        (call.args[1], call.args[2].id) for call in mock_genenerate_monthly_charges.call_args_list
    ]
    assert sorted(actual_calls_args) == sorted(expected_calls_args)


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_monthly_charges_dry_run(
    exchange_rates_factory: ModelFactory[ExchangeRates],
    usd_org_billed_in_eur_expenses: Organization,
    operations_account: Account,
    db_session: AsyncSession,
    tmp_path: pathlib.Path,
    mocker: MockerFixture,
    snapshot: Snapshot,
    caplog: pytest.LogCaptureFixture,
):
    mock_upload_to_azure = mocker.patch(
        "app.commands.generate_monthly_charges.upload_charges_file_to_azure"
    )
    charges_file_handler = ChargesFileHandler(db_session)
    assert await charges_file_handler.count() == 0

    await exchange_rates_factory(base_currency="EUR")
    await exchange_rates_factory(base_currency="USD")
    await exchange_rates_factory(base_currency="GBP")

    with caplog.at_level(logging.INFO):
        await generate_monthly_charges_main(
            exports_dir=tmp_path,
            account_id=operations_account.id,
            currency="EUR",
            dry_run=True,
        )

    assert "Dry run enabled, skipping upload to Azure Blob Storage" in caplog.text
    assert "Dry run enabled, skipping creating charges file database record" in caplog.text
    assert "Dry run enabled, skipping fetching existing charges file" in caplog.text

    assert not mock_upload_to_azure.called
    assert await charges_file_handler.count() == 0
    expected_generated_file_path = tmp_path / f"{operations_account.id}_EUR_2025_04.zip"
    assert expected_generated_file_path.exists()

    with zipfile.ZipFile(expected_generated_file_path, "r") as archive:
        assert sorted(archive.namelist()) == ["charges.xlsx", "exchange_rates_USD.json"]

        excel_file_path = pathlib.Path(archive.extract("charges.xlsx", tmp_path))
        assert_generated_file_matches_snapshot(excel_file_path, snapshot)


def test_cli_command(mocker: MockerFixture, test_settings: Settings, tmp_path: pathlib.Path):
    mocker.patch("app.cli.get_settings", return_value=test_settings)
    mock_command_coro = mocker.MagicMock()
    mock_command = mocker.MagicMock(return_value=mock_command_coro)

    mocker.patch("app.commands.generate_monthly_charges.main", mock_command)
    mock_run = mocker.patch("app.commands.generate_monthly_charges.asyncio.run")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-monthly-charges", "--exports-dir", str(tmp_path)])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(mock_command_coro)
    mock_command.assert_called_once_with(
        exports_dir=tmp_path,
        currency=None,
        account_id=None,
        dry_run=False,
    )


def test_cli_command_default_exports_dir(mocker: MockerFixture, test_settings: Settings):
    mocker.patch("app.cli.get_settings", return_value=test_settings)
    mock_command_coro = mocker.MagicMock()
    mock_command = mocker.MagicMock(return_value=mock_command_coro)

    mocker.patch("app.commands.generate_monthly_charges.main", mock_command)
    mock_run = mocker.patch("app.commands.generate_monthly_charges.asyncio.run")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-monthly-charges"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(mock_command_coro)

    calls = mock_command.call_args_list
    assert len(calls) == 1
    exports_dir = calls[0].kwargs.get("exports_dir")
    assert exports_dir.is_relative_to(tempfile.gettempdir())
