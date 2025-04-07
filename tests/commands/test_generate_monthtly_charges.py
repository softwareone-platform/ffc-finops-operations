import io
from decimal import Decimal

import pytest
from pytest_snapshot.plugin import Snapshot
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.generate_monthly_charges import ChargesFileGenerator
from app.currency import CurrencyConverter
from app.db.models import Account, DatasourceExpense, Entitlement, Organization
from app.enums import AccountType, EntitlementStatus, OrganizationStatus
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


@pytest.mark.fixed_random_seed
async def test_generate_charges_file_csv_operations_same_currency(
    currency_converter: CurrencyConverter,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    db_session: AsyncSession,
    operations_account: Account,
    snapshot: Snapshot,
):
    organization = await organization_factory(
        operations_external_id="org1",
        name="Organization 1",
        status=OrganizationStatus.ACTIVE,
        currency="USD",
        billing_currency="USD",
        linked_organization_id="organization_id_1",
    )
    ds_exp_1 = await datasource_expense_factory(  # noqa: F841
        datasource_id="ds_id1",
        datasource_name="Datasource 1",
        organization=organization,
        month=2,
        year=2025,
        month_expenses=Decimal("50.00"),
    )
    ds_exp_2 = await datasource_expense_factory(  # noqa: F841
        datasource_id="ds_id1",
        datasource_name="Datasource 1",
        organization=organization,
        month=3,
        year=2025,
        month_expenses=Decimal("60.00"),
    )
    ds_exp_3 = await datasource_expense_factory(
        datasource_id="ds_id2",
        datasource_name="Datasource 2",
        organization=organization,
        month=3,
        year=2025,
        month_expenses=Decimal("70.00"),
    )
    await entitlement_factory(
        name="entitlement_1",
        status=EntitlementStatus.ACTIVE,
        affiliate_external_id="EXTERNAL_ID_1",
        datasource_id="ds_id2",
    )

    # Load the entitlement relationship to the datasource expense model
    await db_session.refresh(ds_exp_3)

    file = io.StringIO()
    charges_file_generator = ChargesFileGenerator(operations_account, "USD", currency_converter)
    created = await charges_file_generator.generate_charges_file(file)

    assert created

    file.seek(0)
    snapshot.assert_match(file.read(), "charge_files.csv")


@pytest.mark.fixed_random_seed
async def test_generate_charges_file_csv_affiliate_same_currency(
    currency_converter: CurrencyConverter,
    organization_factory: ModelFactory[Organization],
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    entitlement_factory: ModelFactory[Entitlement],
    db_session: AsyncSession,
    affiliate_account: Account,
    account_factory: ModelFactory[Account],
    snapshot: Snapshot,
):
    organization = await organization_factory(
        operations_external_id="org1",
        name="Organization 1",
        status=OrganizationStatus.ACTIVE,
        currency="USD",
        billing_currency="USD",
        linked_organization_id="organization_id_1",
    )
    ds_exp_1 = await datasource_expense_factory(  # noqa: F841
        datasource_id="ds_id1",
        datasource_name="Datasource 1",
        organization=organization,
        month=2,
        year=2025,
        month_expenses=Decimal("50.00"),
    )
    ds_exp_2 = await datasource_expense_factory(  # noqa: F841
        datasource_id="ds_id1",
        datasource_name="Datasource 1",
        organization=organization,
        month=3,
        year=2025,
        month_expenses=Decimal("60.00"),
    )
    ds_exp_3 = await datasource_expense_factory(
        datasource_id="ds_id2",
        datasource_name="Datasource 2",
        organization=organization,
        month=3,
        year=2025,
        month_expenses=Decimal("70.00"),
    )
    another_affiliate_account = await account_factory(type=AccountType.AFFILIATE)

    await entitlement_factory(
        name="entitlement_1",
        affiliate_external_id="EXTERNAL_ID_1",
        datasource_id="ds_id2",
        status=EntitlementStatus.ACTIVE,
        owner=affiliate_account,
    )

    await entitlement_factory(
        name="entitlement_2",
        affiliate_external_id="EXTERNAL_ID_2",
        datasource_id="ds_id2",
        status=EntitlementStatus.ACTIVE,
        owner=another_affiliate_account,
    )

    # Load the entitlement relationship to the datasource expense model
    await db_session.refresh(ds_exp_3)

    file = io.StringIO()
    charges_file_generator = ChargesFileGenerator(affiliate_account, "USD", currency_converter)
    created = await charges_file_generator.generate_charges_file(file)

    assert created

    file.seek(0)
    snapshot.assert_match(file.read(), "charge_files.csv")
