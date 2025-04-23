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
from azure.core.exceptions import AzureError, ClientAuthenticationError, ResourceNotFoundError
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.blob_storage import upload_charges_file
from app.conf import Settings, get_settings
from app.currency import CurrencyConverter
from app.db.base import session_factory
from app.db.handlers import (
    AccountHandler,
    ChargesFileHandler,
    DatasourceExpenseHandler,
    OrganizationHandler,
)
from app.db.models import Account, ChargesFile, DatasourceExpense, Organization
from app.enums import AccountType, ChargesFileStatus, EntitlementStatus

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

    def generate_charges_file_dataframe(
        self, datasource_expenses: Sequence[DatasourceExpense]
    ) -> pd.DataFrame | None:
        logger.info(
            "Generating charges file contents for account %s and currency %s",
            self.account.id,
            self.currency,
        )

        charge_entries = self.get_charge_entries(datasource_expenses)

        if not charge_entries:
            logger.warning(
                "No charge entries found for account %s and currency %s, "
                "skipping generating charges file as it would be empty",
                self.account.id,
                self.currency,
            )
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

        logger.info(
            "Charges file contents for account %s and currency %s generated successfully",
            self.account.id,
            self.currency,
        )

        return df

    def export_to_excel(self, df: pd.DataFrame, filename: str) -> pathlib.Path:
        logger.info(
            "Exporting charge file contents for account %s and currency %s to excel format",
            self.account.id,
            self.currency,
        )
        filepath = self.exports_dir / filename

        df.to_excel(filepath, header=True, index=False)

        logger.info(
            "Charge file contents for account %s and currency %s "
            "exported to excel format and saved at %s",
            self.account.id,
            self.currency,
            str(filepath.resolve()),
        )

        return filepath

    def export_to_zip(self, df: pd.DataFrame, filename: str) -> pathlib.Path:
        filepath = self.exports_dir / filename

        logger.info(
            "Exporting charge file contents together with the currency conversion rates "
            "for account %s and currency %s to zip format",
            self.account.id,
            self.currency,
        )

        excel_filepath = self.export_to_excel(df, filename="charges.xlsx")

        with zipfile.ZipFile(filepath, mode="w") as archive:
            archive.write(excel_filepath, arcname=excel_filepath.name)
            archive.writestr(
                f"exchange_rates_{self.currency_converter.base_currency}.json",
                self.currency_converter.get_exchangerate_api_response_json(),
            )

        excel_filepath.unlink(missing_ok=True)

        logger.info(
            "Charges file ZIP generated for account %s and currency %s and saved to %s",
            self.account.id,
            self.currency,
            str(filepath.resolve()),
        )

        return filepath

    @staticmethod
    def get_total_amount(df: pd.DataFrame) -> Decimal:
        return df["Total Purchase Price"].sum()


async def upload_charges_file_to_azure(charges_file: ChargesFile, filepath: pathlib.Path) -> bool:
    logging.info(
        "Uploading the charges file %s at %s to Azure Blob Storage",
        charges_file.id,
        filepath,
    )

    try:
        await upload_charges_file(
            file_path=str(filepath.resolve()),
            currency=charges_file.currency,
            month=charges_file.document_date.month,
            year=charges_file.document_date.year,
        )

        logger.info(
            "Charges file %s successfully uploaded to Azure Blob Storage, blob name: %s",
            charges_file.id,
            charges_file.azure_blob_name,
        )

        return True
    except (ResourceNotFoundError, AzureError, ClientAuthenticationError):
        logger.exception("Unable to upload any files to Azure Blob Storage, aborting the process")
        # raising the exception as we need to stop the process -- all the other uploads
        # will fail too
        raise
    except Exception:
        logger.exception(
            "Unexpected error occurred while uploading %s to Azure, skipping this file",
            str(filepath.resolve()),
        )

    return False


async def fetch_existing_generated_charges_file(
    session: AsyncSession, account: Account, currency: str
) -> ChargesFile | None:
    logger.info(
        "Checking if the charges file for account %s and currency %s is already generated",
        account.id,
        currency,
    )

    charges_file_handler = ChargesFileHandler(session)
    today = datetime.now(UTC).date()

    latest_matching_generated_charge_file_stmt = (
        select(ChargesFile)
        .where(
            (ChargesFile.owner == account)
            & (ChargesFile.currency == currency)
            & (ChargesFile.status.in_([ChargesFileStatus.GENERATED, ChargesFileStatus.PROCESSED]))
            & (extract("year", ChargesFile.document_date) == today.year)
            & (extract("month", ChargesFile.document_date) == today.month)
        )
        .order_by(ChargesFile.document_date.desc())
        .limit(1)
    )

    generated_charges_file = await charges_file_handler.first(
        latest_matching_generated_charge_file_stmt
    )

    if generated_charges_file is None:
        logger.info(
            "Charges file for account %s and currency %s hasn't been generated yet, "
            "proceeding to generate it",
            account.id,
            currency,
        )
    else:
        logger.info(
            "Charges file for account %s and currency %s already exists (%s) "
            "and it's in %s status, skipping generating a new one",
            account.id,
            currency,
            generated_charges_file.id,
            generated_charges_file.status.value,
        )

    return generated_charges_file


async def fetch_datasource_expenses(
    session: AsyncSession, account: Account, currency: str
) -> Sequence[DatasourceExpense]:
    today = datetime.now(UTC).date()
    last_month = today - relativedelta(months=1)

    organization_handler = OrganizationHandler(session)
    datasource_expense_handler = DatasourceExpenseHandler(session)

    logger.info(
        "Querying organizations to process for account %s with billing currency = %s",
        account.id,
        currency,
    )

    organizations = await organization_handler.query_db(
        where_clauses=[Organization.billing_currency == currency]
    )
    logger.info(
        "Found %d organizations to process for billing currency %s",
        len(organizations),
        currency,
    )

    logger.info(
        "Querying datasource expenses for all organizations "
        "with %s billing currency for month = %s, year = %s",
        currency,
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
        "Found %d datasource expenses for all organizations "
        "with %s billing currency for month = %s, year = %s",
        len(all_orgs_expenses),
        currency,
        last_month.month,
        last_month.year,
    )

    return all_orgs_expenses


async def fetch_unique_billing_currencies(session: AsyncSession) -> Sequence[str]:
    """Fetch unique billing currencies from the database."""

    logger.info("Fetching all the unique billing currencies from the database")

    currencies_stmt = (
        select(Organization.billing_currency)
        .distinct()
        .order_by(Organization.billing_currency.asc())
    )

    currencies = (await session.scalars(currencies_stmt)).all()

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


async def get_or_create_draft_charges_file(
    session: AsyncSession, account: Account, currency: str, document_date: date
) -> ChargesFile:
    charges_file_handler = ChargesFileHandler(session)

    logger.info(
        "Checking if a database record for the charges file for "
        "account %s and currency %s already exists in draft status",
        account.id,
        currency,
    )

    charges_file, created = await charges_file_handler.get_or_create(
        owner=account,
        currency=currency,
        status=ChargesFileStatus.DRAFT,
        extra_conditions=[
            extract("year", ChargesFile.document_date) == document_date.year,
            extract("month", ChargesFile.document_date) == document_date.month,
        ],
        defaults={
            "amount": None,
            "document_date": document_date,
        },
    )

    if created:
        logger.info(
            "Charges file database record created for account %s and currency %s "
            "in DRAFT status: %s",
            account.id,
            currency,
            charges_file.id,
        )
    else:
        logger.info(
            "Charges file database record for account %s and currency %s "
            "already exists in DRAFT status: %s, re-using it",
            account.id,
            currency,
            charges_file.id,
        )

    return charges_file


async def update_charges_file_post_generation(
    session: AsyncSession, charges_file: ChargesFile, amount: Decimal
) -> None:
    charges_file_handler = ChargesFileHandler(session)

    logger.info(
        "Updating the charges file %s in the database to status %s",
        charges_file.id,
        ChargesFileStatus.GENERATED,
    )

    await charges_file_handler.update(
        charges_file,
        {
            "amount": amount,
            "status": ChargesFileStatus.GENERATED,
        },
    )

    logger.info(
        "Charges file %s updated in the database to status %s with amount %s",
        charges_file.id,
        ChargesFileStatus.GENERATED,
        charges_file.amount,
    )


async def main(exports_dir: pathlib.Path, settings: Settings) -> None:
    today = datetime.now(UTC).date()

    async with session_factory() as session:
        async with session.begin():
            unique_billing_currencies = await fetch_unique_billing_currencies(session)
            currency_converter = await CurrencyConverter.from_db(session)
            accounts = await fetch_accounts(session)

        for currency in unique_billing_currencies:
            for account in accounts:
                charges_file_generator = ChargesFileGenerator(
                    account, currency, currency_converter, exports_dir
                )

                async with session.begin():
                    generated_charges_file = await fetch_existing_generated_charges_file(
                        session, account, currency
                    )

                if generated_charges_file is not None:
                    continue

                async with session.begin():
                    datasource_expenses = await fetch_datasource_expenses(
                        session, account, currency
                    )

                df = charges_file_generator.generate_charges_file_dataframe(datasource_expenses)

                if df is None:
                    continue

                async with session.begin():
                    charges_file_db_record = await get_or_create_draft_charges_file(
                        session, account, currency, today
                    )

                exported_filepath = charges_file_generator.export_to_zip(
                    df, filename=f"{charges_file_db_record.id}.zip"
                )

                successful_upload = await upload_charges_file_to_azure(
                    charges_file_db_record, exported_filepath
                )

                if not successful_upload:  # pragma: no cover
                    continue

                async with session.begin():
                    await update_charges_file_post_generation(
                        session,
                        charges_file_db_record,
                        amount=charges_file_generator.get_total_amount(df),
                    )


def command(
    ctx: typer.Context,
    exports_dir: Annotated[
        pathlib.Path, typer.Option("--exports-dir", help="Directory to export the charge files to")
    ],
) -> None:
    """
    Generate monthly charges for all accounts and currencies.
    """
    logger.info("Starting command function")

    if exports_dir.is_file():  # pragma: no cover
        raise ValueError("The exports directory must be a directory, not a file.")

    if not exports_dir.exists():  # pragma: no cover
        logger.info("Exports directory %s does not exist, creating it", str(exports_dir.resolve()))
        exports_dir.mkdir(parents=True)

    asyncio.run(main(exports_dir, ctx.obj))

    logger.info("Completed command function")
