import asyncio
import logging
import pathlib
import zipfile
from collections.abc import Sequence
from copy import copy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Self

import pandas as pd
import typer
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session

from app.conf import Settings, get_settings
from app.currency import CurrencyConverter
from app.db.base import session_factory
from app.db.handlers import (
    AccountHandler,
    DatasourceExpenseHandler,
    OrganizationHandler,
)
from app.db.models import Account, DatasourceExpense, Organization
from app.enums import AccountType, EntitlementStatus

logger = logging.getLogger(__name__)


@dataclass
class ChargeEntry:
    subscription_search_criteria: str
    subscription_search_value: str
    item_search_criteria: str
    item_search_value: str
    usage_start_time: date
    usage_end_time: date
    price: Decimal
    external_reference: str
    vendor_description_1: str
    vendor_description_2: str
    vendor_reference: str

    @classmethod
    def from_datasource_expense(
        cls, exp: DatasourceExpense, currency_converter: CurrencyConverter
    ) -> Self:
        settings = get_settings()

        if exp.organization.linked_organization_id is None:
            raise ValueError(
                f"Cannot generate charge for datasource expense {exp.id}: "
                f"Organization {exp.organization.id} does not have a linked organization ID."
            )

        usage_start = max(datetime(exp.year, exp.month, 1).date(), exp.created_at.date())
        usage_end = min(usage_start + relativedelta(day=31), exp.updated_at.date())

        price = currency_converter.convert_currency(
            exp.month_expenses * Decimal(settings.billing_percentage) / 100,
            from_currency=exp.organization.currency,
            to_currency=exp.organization.billing_currency,
        )

        return cls(
            subscription_search_criteria="subscription.externalIds.vendor",
            subscription_search_value=exp.organization_id,
            item_search_criteria="item.externalIds.vendor",
            item_search_value=settings.ffc_external_product_id,
            usage_start_time=usage_start,
            usage_end_time=usage_end,
            price=price,
            external_reference=exp.organization.linked_organization_id,
            vendor_description_1=exp.datasource_name,
            vendor_description_2=exp.datasource_id,
            vendor_reference="",
        )

    def contra_entry(self) -> Self:
        contra_entry = copy(self)
        contra_entry.price = -self.price

        return contra_entry


@dataclass
class ChargesFileGenerator:
    account: Account
    currency: str
    currency_converter: CurrencyConverter
    exports_dir: pathlib.Path

    async def fetch_datasource_expenses(self) -> Sequence[DatasourceExpense]:
        today = datetime.now(UTC).date()
        last_month = today - relativedelta(months=1)

        session = async_object_session(self.account)

        if session is None:  # pragma: no cover
            # This can happen if we only create an account python object but we haven't yet
            # added it to the database. If that's the case, that's incrrect usage of the class,
            # so we should raise an error.

            raise ValueError(
                "Account must be associated with a session to fetch datasource expenses."
            )

        organization_handler = OrganizationHandler(session)
        datasource_expense_handler = DatasourceExpenseHandler(session)

        logger.info(
            "Querying organizations to process for account %s with billing currency = %s",
            self.account.id,
            self.currency,
        )

        organizations = await organization_handler.query_db(
            where_clauses=[Organization.billing_currency == self.currency]
        )
        logger.info("Found %d organizations to process", len(organizations))

        logger.info(
            "Querying datasource expenses for all organization for month = %s, year = %s",
            last_month.month,
            last_month.year,
        )
        all_orgs_expenses = await datasource_expense_handler.query_db(
            where_clauses=[
                DatasourceExpense.organization_id.in_(org.id for org in organizations),
                DatasourceExpense.month == last_month.month,
                DatasourceExpense.year == last_month.year,
            ],
            unique=True,
        )
        logger.info(
            "Found %d datasource expenses for all organization for month = %s, year = %s",
            len(all_orgs_expenses),
            last_month.month,
            last_month.year,
        )

        return all_orgs_expenses

    def get_charge_entries(
        self, datasource_expenses: Sequence[DatasourceExpense]
    ) -> list[ChargeEntry]:
        return [
            charge_entry
            for ds_exp in datasource_expenses
            for charge_entry in self.charge_entries_for_datasource_expense(ds_exp)
        ]

    def charge_entries_for_datasource_expense(
        self, datasource_expense: DatasourceExpense
    ) -> list[ChargeEntry]:
        entry = ChargeEntry.from_datasource_expense(datasource_expense, self.currency_converter)

        if self.account.type == AccountType.AFFILIATE:
            for entitlement in datasource_expense.entitlements:
                if entitlement.owner != self.account:
                    continue

                if entitlement.status != EntitlementStatus.ACTIVE:
                    continue

                # If multiple entitlements match the same datasource expense, we need to
                # return only the first one (the entitlements are already ordered by
                # created_at)
                return [entry]

            return []

        if self.account.type == AccountType.OPERATIONS:
            charge_entries = [entry]

            for entitlement in datasource_expense.entitlements:
                if entitlement.status != EntitlementStatus.ACTIVE:
                    continue

                charge_entries.append(entry.contra_entry())

                # If multiple entitlements match the same datasource expense, we need to
                # add only the contra entry for the first one (the entitlements are
                # already ordered by created_at)
                break

            return charge_entries

        raise ValueError(f"Unknown account type: {self.account.type}")  # pragma: no cover

    async def generate_charges_file_dataframe(self) -> pd.DataFrame | None:
        datasource_expenses = await self.fetch_datasource_expenses()
        charge_entries = self.get_charge_entries(datasource_expenses)

        if not charge_entries:
            return None

        df = pd.DataFrame(
            [
                {
                    "Entry ID": row_num,
                    "Subscription Search Criteria": "subscription.externalIds.vendor",
                    "Subscription Search Value": entry.subscription_search_value,
                    "Item Search Criteria": "item.externalIds.vendor",
                    "Item Search Value": entry.item_search_value,
                    "Usage Start Time": entry.usage_start_time.strftime("%-d-%b-%Y"),
                    "Usage End Time": entry.usage_end_time.strftime("%-d-%b-%Y"),
                    "Quantity": 1,
                    "Purchase Price": entry.price.quantize(Decimal("0.01")),
                    "Total Purchase Price": entry.price.quantize(Decimal("0.01")),
                    "External Reference": entry.external_reference,
                    "Vendor Description 1": entry.vendor_description_1,
                    "Vendor Description 2": entry.vendor_description_2,
                    "Vendor Reference": "",
                }
                for row_num, entry in enumerate(charge_entries, start=1)
            ]
        )

        return df

    def export_to_excel(self, df: pd.DataFrame) -> pathlib.Path:
        last_month = datetime.now(UTC).date() - relativedelta(months=1)
        filename = (
            f"charges_{self.account.id}_{self.currency}_"
            f"{last_month.year}_{last_month.month:02d}.xlsx"
        )
        filepath = self.exports_dir / filename

        df.to_excel(filepath, header=True, index=False)

        return filepath

    def export_to_zip(self, df: pd.DataFrame) -> pathlib.Path:
        excel_filepath = self.export_to_excel(df)
        filepath = self.exports_dir / (excel_filepath.stem + ".zip")

        with zipfile.ZipFile(filepath, mode="w") as archive:
            archive.write(self.export_to_excel(df), arcname=excel_filepath.name)
            archive.writestr(
                f"exchange_rates_{self.currency}.json",
                self.currency_converter.get_exchangerate_api_response_json(),
            )

        excel_filepath.unlink(missing_ok=True)

        return filepath


async def fetch_unique_billing_currencies(session: AsyncSession) -> Sequence[str]:
    """Fetch unique billing currencies from the database."""

    logger.info(
        "Fetching all the unique billing currencies",
    )

    currencies = (await session.scalars(select(Organization.billing_currency).distinct())).all()

    logger.info(
        "Found the following unique billing currencies from the database: %s",
        ", ".join(currencies),
    )
    return currencies


async def fetch_accounts(session: AsyncSession) -> Sequence[Account]:
    """Fetch all accounts from the database."""

    logger.info("Fetching all the accounts")
    account_handler = AccountHandler(session)
    accounts = await account_handler.query_db(unique=True)

    logger.info("Found %d accounts in the database", len(accounts))
    return accounts


# NOTE: This is still work in progress as we need to implement the items bellow. As such, the
# main function only functions as a usage example and not the final implmentation, thus the
# pragma: no cover. Once this is finalized the function will be covered by the tests like any other.
#
# Remaining work:
#   - MPT-8992: Create the ChargesFile db record for the generated file
#   - MPT-8994: Upload the ZIP file to S3
async def main(exports_dir: pathlib.Path, settings: Settings) -> None:  # pragma: no cover
    if exports_dir.is_file():
        raise ValueError("The exports directory must be a directory, not a file.")

    if not exports_dir.exists():
        logger.info("Exports directory %s does not exist, creating it", str(exports_dir.resolve()))
        exports_dir.mkdir(parents=True)

    async with session_factory() as session:
        unique_billing_currencies = await fetch_unique_billing_currencies(session)
        currency_converter = await CurrencyConverter.from_db(session)
        accounts = await fetch_accounts(session)

        for currency in unique_billing_currencies:
            for account in accounts:
                logger.info(
                    "Generating charges file for account %s and currency %s",
                    account.id,
                    currency,
                )
                charges_file_generator = ChargesFileGenerator(
                    account, currency, currency_converter, exports_dir
                )

                df = await charges_file_generator.generate_charges_file_dataframe()

                if df is None:
                    logger.info(
                        "No charge entries found for account %s and currency %s, "
                        "skipping generating charges file",
                        account.id,
                        currency,
                    )
                    continue

                exported_filepath = charges_file_generator.export_to_excel(df)

                logger.info(
                    "Charges file generated for account %s and currency %s and saved to %s",
                    account.id,
                    currency,
                    str(exported_filepath.resolve()),
                )


def command(
    ctx: typer.Context,
    exports_dir: Annotated[
        pathlib.Path, typer.Option("--exports-dir", help="Directory to export the charge files to")
    ],
) -> None:  # pragma: no cover
    """
    Generate monthly charges for all accounts and currencies.
    """
    logger.info("Starting command function")
    asyncio.run(main(exports_dir, ctx.obj))
    logger.info("Completed command function")
