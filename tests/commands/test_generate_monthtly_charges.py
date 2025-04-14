import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import time_machine
from faker import Faker
from pytest_snapshot.plugin import Snapshot
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.generate_monthly_charges import (
    ChargeEntry,
    ChargesFileGenerator,
    fetch_accounts,
    fetch_unique_billing_currencies,
)
from app.conf import Settings
from app.currency import CurrencyConverter
from app.db.models import Account, DatasourceExpense, Entitlement, Organization
from app.enums import AccountStatus, AccountType, EntitlementStatus, OrganizationStatus
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
async def usd_org_billed_in_eur_expenses(
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    affiliate_account: Account,
    account_factory: ModelFactory[Account],
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
    another_affiliate_account = await account_factory(type=AccountType.AFFILIATE)

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
    account_factory: ModelFactory[Account],
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
    account_factory: ModelFactory[Account],
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


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_charges_file_csv_operations_same_currency(
    currency_converter: CurrencyConverter,
    operations_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    snapshot: Snapshot,
):
    file = io.StringIO()
    charges_file_generator = ChargesFileGenerator(operations_account, "USD", currency_converter)
    created = await charges_file_generator.generate_charges_file(file)

    assert created

    file.seek(0)
    snapshot.assert_match(file.read(), "charges_file.csv")


@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_charges_file_csv_affiliate_same_currency(
    currency_converter: CurrencyConverter,
    affiliate_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    snapshot: Snapshot,
):
    file = io.StringIO()
    charges_file_generator = ChargesFileGenerator(affiliate_account, "USD", currency_converter)
    created = await charges_file_generator.generate_charges_file(file)

    assert created

    file.seek(0)
    snapshot.assert_match(file.read(), "charges_file.csv")


async def test_generate_charges_file_csv_empty_file(
    currency_converter: CurrencyConverter,
    usd_org_billed_in_usd_expenses: Organization,
    affiliate_account: Account,
):
    file = io.StringIO()
    charges_file_generator = ChargesFileGenerator(affiliate_account, "EUR", currency_converter)
    created = await charges_file_generator.generate_charges_file(file)

    assert not created

    file.seek(0)
    assert file.read() == ""


@pytest.mark.parametrize(
    "currency",
    ["USD", "EUR", "GBP"],
)
@pytest.mark.fixed_random_seed
@time_machine.travel("2025-04-10T10:00:00Z", tick=False)
async def test_generate_charges_file_csv_affiliate_multiple_organizations_and_currencies(
    currency_converter: CurrencyConverter,
    affiliate_account: Account,
    usd_org_billed_in_usd_expenses: Organization,
    usd_org_billed_in_eur_expenses: Organization,
    eur_org_billed_in_gbp_expenses: Organization,
    snapshot: Snapshot,
    currency: str,
):
    file = io.StringIO()
    charges_file_generator = ChargesFileGenerator(affiliate_account, currency, currency_converter)
    created = await charges_file_generator.generate_charges_file(file)

    assert created

    file.seek(0)
    snapshot.assert_match(file.read(), f"charges_file_{currency}.csv")


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
