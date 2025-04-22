import io
import logging
import pathlib
import zipfile
from datetime import UTC, date, datetime
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
    EntitlementStatus,
    OrganizationStatus,
)
from tests.conftest import ModelFactory


@pytest.fixture
def currency_converter() -> CurrencyConverter:
    return CurrencyConverter(
        base_currency="USD",
        exchange_rates={
            "EUR": Decimal("0.9252"),
            "GBP": Decimal("0.7737"),
        },
    )


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
        datasource_id=faker.uuid4(str),
        datasource_name="AWS Account",
        organization=org,
        month=2,
        year=2025,
        month_expenses=Decimal("50.00"),
        created_at=datetime(2025, 2, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 2, 28, 10, 0, 0, tzinfo=UTC),
    )
    aws_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id=aws_acc_feb_expenses.datasource_id,
        datasource_name=aws_acc_feb_expenses.datasource_name,
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("60.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )
    gcp_acc_mar_expenses = await datasource_expense_factory(
        datasource_id=faker.uuid4(str),
        datasource_name="GCP Account",
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("70.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="free GCP account",
        affiliate_external_id="ACC-11111",
        datasource_id=gcp_acc_mar_expenses.datasource_id,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    # Should be ignored
    await entitlement_factory(
        name="free AWS account",
        affiliate_external_id="ACC-22222",
        datasource_id=aws_acc_mar_expenses.datasource_id,
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
        datasource_id=faker.uuid4(str),
        datasource_name="AWS Account",
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("50.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    azure_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id=faker.uuid4(str),
        datasource_name="Azure Account",
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("40.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="Free AWS account",
        affiliate_external_id="ACC-33333",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        status=EntitlementStatus.TERMINATED,  # should be ignored
        owner=affiliate_account,
    )

    await entitlement_factory(
        name="Free Azure account",
        affiliate_external_id="ACC-44444",
        datasource_id=azure_acc_mar_expenses.datasource_id,
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
        datasource_id=faker.uuid4(str),
        datasource_name="AWS Account",
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("60.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )
    gcp_acc_mar_expenses = await datasource_expense_factory(
        datasource_id=faker.uuid4(str),
        datasource_name="GCP Account",
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("70.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )
    azure_acc_mar_expenses = await datasource_expense_factory(  # noqa: F841
        datasource_id=faker.uuid4(str),
        datasource_name="Azure Account",
        organization=org,
        month=3,
        year=2025,
        month_expenses=Decimal("40.00"),
        created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 31, 10, 0, 0, tzinfo=UTC),
    )

    await entitlement_factory(
        name="free AWS account",
        affiliate_external_id="ACC-55555",
        datasource_id=aws_acc_mar_expenses.datasource_id,
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    # Should be ignored
    await entitlement_factory(
        name="free GCP account",
        affiliate_external_id="ACC-66666",
        datasource_id=gcp_acc_mar_expenses.datasource_id,
        status=EntitlementStatus.TERMINATED,
        owner=affiliate_account,
    )


def assert_df_matches_snapshot(df: pd.DataFrame, snapshot: Snapshot) -> None:
    # We're exporting the dataframe to CSV format, so that we can save it in a snapshot file.
    # We're intentionally using CSV instead of Excel format, as .xlsx is a binary format and
    # should the test fail, the diff would be unreadable and won't be obvious what's wrong.
    # There is a seperate test specifically for the excel exporting

    file = io.StringIO()
    df.to_csv(file, index=False, header=True)

    file.seek(0)
    snapshot.assert_match(file.read(), "charges.csv")


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
    charges_file_generator = ChargesFileGenerator(
        operations_account, "USD", currency_converter, tmp_path
    )
    datasource_expenses = await fetch_datasource_expenses(db_session, operations_account, "USD")
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)
    assert_df_matches_snapshot(df, snapshot)


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
    charges_file_generator = ChargesFileGenerator(
        affiliate_account, "USD", currency_converter, tmp_path
    )
    datasource_expenses = await fetch_datasource_expenses(db_session, affiliate_account, "USD")
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)
    assert_df_matches_snapshot(df, snapshot)


async def test_generate_charges_file_dataframe_empty_file(
    currency_converter: CurrencyConverter,
    usd_org_billed_in_usd_expenses: Organization,
    affiliate_account: Account,
    db_session: AsyncSession,
    tmp_path: pathlib.Path,
):
    charges_file_generator = ChargesFileGenerator(
        affiliate_account, "EUR", currency_converter, tmp_path
    )
    datasource_expenses = await fetch_datasource_expenses(db_session, affiliate_account, "EUR")
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)
    assert df is None


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
    charges_file_generator = ChargesFileGenerator(
        affiliate_account, currency, currency_converter, tmp_path
    )
    datasource_expenses = await fetch_datasource_expenses(db_session, affiliate_account, currency)
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)
    assert_df_matches_snapshot(df, snapshot)


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_export_to_excel(
    currency_converter: CurrencyConverter,
    operations_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    db_session: AsyncSession,
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
):
    charges_file_generator = ChargesFileGenerator(
        operations_account, "USD", currency_converter, tmp_path
    )
    datasource_expenses = await fetch_datasource_expenses(db_session, operations_account, "USD")
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)
    assert df is not None

    filepath = charges_file_generator.export_to_excel(df, "charges.xlsx")

    assert filepath.name == "charges.xlsx"
    assert filepath.parent == tmp_path
    snapshot.assert_match(filepath.read_bytes(), "charges.xlsx")


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_export_to_zip(
    exchange_rates_factory: ModelFactory[ExchangeRates],
    operations_account: Account,
    usd_org_billed_in_eur_expenses: Organization,
    db_session: AsyncSession,
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
):
    await exchange_rates_factory(
        base_currency="USD",
        exchange_rates={
            "EUR": 0.9252,
            "GBP": 0.7737,
        },
    )

    currency_converter = await CurrencyConverter.from_db(db_session)

    charges_file_generator = ChargesFileGenerator(
        operations_account, "EUR", currency_converter, tmp_path
    )

    datasource_expenses = await fetch_datasource_expenses(db_session, operations_account, "EUR")
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)
    assert df is not None

    filepath = charges_file_generator.export_to_zip(df, filename="charges.zip")

    assert filepath.name == "charges.zip"
    assert filepath.parent == tmp_path

    with zipfile.ZipFile(filepath, "r") as archive:
        assert sorted(archive.namelist()) == ["charges.xlsx", "exchange_rates_USD.json"]

        snapshot.assert_match(archive.read("charges.xlsx"), "charges.xlsx")
        snapshot.assert_match(archive.read("exchange_rates_USD.json"), "exchange_rates.json")


@pytest.mark.parametrize(
    ("currency", "expected_total_amount"),
    [
        ("USD", Decimal("1.10")),
        ("EUR", Decimal("0.00")),
        ("GBP", Decimal("0.42")),
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
    snapshot: Snapshot,
    tmp_path: pathlib.Path,
    db_session: AsyncSession,
    currency: str,
    expected_total_amount: Decimal,
):
    charges_file_generator = ChargesFileGenerator(
        operations_account, currency, currency_converter, tmp_path
    )
    datasource_expenses = await fetch_datasource_expenses(db_session, operations_account, currency)
    df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)

    assert df is not None

    total_amount = charges_file_generator.get_total_amount(df)

    assert total_amount == expected_total_amount
    assert total_amount == df["Purchase Price"].sum()  # type: ignore[index]
    assert total_amount == df["Total Purchase Price"].sum()  # type: ignore[index]


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
async def test_upload_to_azure(
    currency_converter: CurrencyConverter,
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
    charges_file_generator = ChargesFileGenerator(
        operations_account, "USD", currency_converter, tmp_path
    )

    dummy_file = tmp_path / "dummy_file.xlsx"
    dummy_file.touch()

    if should_raise:
        assert isinstance(side_effect, Exception)

        with pytest.raises(side_effect.__class__, match=str(side_effect)):
            await charges_file_generator.upload_to_azure(dummy_file, month=4, year=2025)
    else:
        result = await charges_file_generator.upload_to_azure(dummy_file, month=4, year=2025)
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
        month_expenses=Decimal("100.00"),  # 100, so that it's easy to calculate
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
        month_expenses=Decimal("100.00"),  # 100, so that it's easy to calculate
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

    await exchange_rates_factory(
        base_currency="USD",
        exchange_rates={
            "EUR": 0.9252,
            "GBP": 0.7737,
        },
    )

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
    time_machine.travel("2025-04-10T11:00:00Z").start()

    with caplog.at_level(logging.INFO):
        await generate_monthly_charges_main(tmp_path, test_settings)

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
            (operations_account.id, "GBP", Decimal("0.4200")),
            (operations_account.id, "USD", Decimal("1.1000")),
            (affiliate_account.id, "GBP", Decimal("0.3300")),
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

    assert "Found 1 organizations to process for billing currency EUR" in found_logs
    assert "Found 1 organizations to process for billing currency GBP" in found_logs
    assert "Found 1 organizations to process for billing currency USD" in found_logs

    assert (
        "Found 2 datasource expenses for all organizations "
        "with EUR billing currency for month = 3, year = 2025"
    ) in found_logs
    assert (
        "Found 2 datasource expenses for all organizations "
        "with GBP billing currency for month = 3, year = 2025"
    ) in found_logs
    assert (
        "Found 3 datasource expenses for all organizations "
        "with USD billing currency for month = 3, year = 2025"
    ) in found_logs

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
    mock_command.assert_called_once_with(tmp_path, test_settings)
