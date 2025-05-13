import asyncio
import logging
import pathlib
import zipfile
from collections.abc import AsyncGenerator, Sequence
from copy import copy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Self

import openpyxl
import typer
from azure.core.exceptions import AzureError, ClientAuthenticationError, ResourceNotFoundError
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.blob_storage import upload_charges_file
from app.conf import get_settings
from app.currency import CurrencyConverter
from app.db.base import session_factory
from app.db.handlers import (
    AccountHandler,
    ChargesFileHandler,
    DatasourceExpenseHandler,
    OrganizationHandler,
)
from app.db.models import Account, ChargesFile, DatasourceExpense, Organization
from app.enums import AccountType, ChargesFileStatus

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


class ChargesFileGenerator:
    def __init__(
        self,
        account: Account,
        currency: str,
        currency_converter: CurrencyConverter,
        exports_dir: pathlib.Path,
    ) -> None:
        self.account = account
        self.currency = currency
        self.currency_converter = currency_converter
        self.exports_dir = exports_dir
        self.workbook = openpyxl.Workbook(write_only=True)
        self.worksheet = self.workbook.create_sheet()
        self.running_total = Decimal(0)
        self.total_rows = 0
        self.source_currencies: set[str] = set()

    @property
    def has_entries(self) -> bool:
        return self.total_rows > 0

    def append_row(self, charge_entry: ChargeEntry) -> None:
        row = {
            "Entry ID": self.total_rows if self.has_entries else 1,
            "Subscription Search Criteria": "subscription.externalIds.vendor",
            "Subscription Search Value": charge_entry.subscription_search_value,
            "Item Search Criteria": "item.externalIds.vendor",
            "Item Search Value": charge_entry.item_search_value,
            "Usage Start Time": charge_entry.usage_start_time.strftime("%-d-%b-%Y"),
            "Usage End Time": charge_entry.usage_end_time.strftime("%-d-%b-%Y"),
            "Quantity": 1,
            "Purchase Price": charge_entry.price.quantize(Decimal("0.01")),
            "Total Purchase Price": charge_entry.price.quantize(Decimal("0.01")),
            "External Reference": charge_entry.external_reference,
            "Vendor Description 1": charge_entry.vendor_description_1,
            "Vendor Description 2": charge_entry.vendor_description_2,
            "Vendor Reference": "",
        }

        if not self.has_entries:
            # Add the header row
            self.worksheet.append(list(row.keys()))
            self.total_rows += 1

        self.worksheet.append(list(row.values()))
        self.total_rows += 1
        self.running_total += charge_entry.price

    def add_datasource_expense(self, datasource_expense: DatasourceExpense) -> None:
        self.source_currencies.add(datasource_expense.organization.currency)
        entry = ChargeEntry.from_datasource_expense(datasource_expense, self.currency_converter)

        if self.account.type == AccountType.AFFILIATE:
            for entitlement in datasource_expense.entitlements:
                if entitlement.owner != self.account:
                    continue

                self.append_row(entry)

                # If multiple entitlements match the same datasource expense, we need to
                # return only the first one (the entitlements are already ordered by
                # created_at)
                return

            return

        if self.account.type == AccountType.OPERATIONS:
            self.append_row(entry)

            for _entitlement in datasource_expense.entitlements:
                self.append_row(entry.contra_entry())

                # If multiple entitlements match the same datasource expense, we need to
                # add only the contra entry for the first one (the entitlements are
                # already ordered by created_at)
                return

            return

        raise ValueError(f"Unknown account type: {self.account.type}")  # pragma: no cover

    def save(self, filename: str) -> pathlib.Path:
        logger.info(
            "Exporting charge file contents for account %s and currency %s to Excel format",
            self.account.id,
            self.currency,
        )
        filepath = self.exports_dir / filename

        self.workbook.save(filepath)

        logger.info(
            "Charges file generated for account %s and currency %s and saved to %s",
            self.account.id,
            self.currency,
            str(filepath.resolve()),
        )

        return filepath

    def make_archive(self, filename: str) -> pathlib.Path:
        if not self.has_entries:
            raise ValueError("Cannot export to zip format: no records found in the charges file")

        logger.info(
            "Exporting charge file contents together with the currency conversion rates "
            "for account %s and currency %s to zip format",
            self.account.id,
            self.currency,
        )

        excel_filepath = self.save("charges.xlsx")
        filepath = self.exports_dir / filename

        with zipfile.ZipFile(filepath, mode="w") as archive:
            archive.write(excel_filepath, arcname="charges.xlsx")

            for source_currency in self.source_currencies:
                if source_currency == self.currency:
                    continue

                archive.writestr(
                    f"exchange_rates_{source_currency}.json",
                    self.currency_converter.get_exchangerate_api_response_json(source_currency),
                )

        excel_filepath.unlink(missing_ok=True)

        logger.info(
            "Charges file ZIP generated for account %s and currency %s and saved to %s",
            self.account.id,
            self.currency,
            str(filepath.resolve()),
        )

        return filepath


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
    session: AsyncSession, currency: str
) -> AsyncGenerator[DatasourceExpense]:
    today = datetime.now(UTC).date()
    last_month = today - relativedelta(months=1)

    organization_handler = OrganizationHandler(session)
    datasource_expense_handler = DatasourceExpenseHandler(session)

    logger.info("Querying organizations to process with billing currency = %s", currency)

    organizations = await organization_handler.query_db(
        where_clauses=[Organization.billing_currency == currency]
    )
    logger.info(
        "Found %d organizations to process with billing currency %s",
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
    all_orgs_expenses = datasource_expense_handler.stream_scalars(
        extra_conditions=[
            DatasourceExpense.organization_id.in_(org.id for org in organizations),
            DatasourceExpense.month == last_month.month,
            DatasourceExpense.year == last_month.year,
        ],
    )

    async for org_exp in all_orgs_expenses:
        yield org_exp


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


async def genenerate_monthly_charges(
    session: AsyncSession,
    currency: str,
    account: Account,
    currency_converter: CurrencyConverter,
    exports_dir: pathlib.Path,
    dry_run: bool,
) -> None:
    today = datetime.now(UTC).date()
    loop = asyncio.get_event_loop()

    async with session.begin():
        if dry_run:
            logger.info("Dry run enabled, skipping fetching existing charges file")
        else:
            generated_charges_file = await fetch_existing_generated_charges_file(
                session, account, currency
            )

            if generated_charges_file is not None:
                return

        generator = ChargesFileGenerator(account, currency, currency_converter, exports_dir)
        async for ds_exp in fetch_datasource_expenses(session, currency):
            await loop.run_in_executor(None, generator.add_datasource_expense, ds_exp)

        if dry_run:
            logger.info("Dry run enabled, skipping creating charges file database record")

            # When in dry_run mode, we don't have access to the the charges_file ID,
            # so we should use a different filename
            filename = f"{account.id}_{currency}_{today.strftime('%Y_%m')}.zip"
        else:
            if not generator.has_entries:
                # Since we're not saving the results to an excel file in this case, we need to
                # explicitly close the temporary file openpyxl created to avoid leaks
                generator.worksheet.close()
                return

            charges_file_db_record = await get_or_create_draft_charges_file(
                session, account, currency, today
            )
            filename = f"{charges_file_db_record.id}.zip"

    zip_file_path = await loop.run_in_executor(None, generator.make_archive, filename)

    if dry_run:
        logger.info("Dry run enabled, skipping upload to Azure Blob Storage")
        return

    successful_upload = await upload_charges_file_to_azure(charges_file_db_record, zip_file_path)

    if not successful_upload:  # pragma: no cover
        return

    async with session.begin():
        await update_charges_file_post_generation(
            session,
            charges_file_db_record,
            amount=generator.running_total.quantize(Decimal("0.01")),
        )


async def main(
    exports_dir: pathlib.Path,
    currency: str | None = None,
    account_id: str | None = None,
    dry_run: bool = False,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            unique_billing_currencies = await fetch_unique_billing_currencies(session)
            currency_converter = await CurrencyConverter.from_db(session)
            accounts = await fetch_accounts(session)

        if currency is not None:
            logger.info("--currency is set, generating charge files only for currency %s", currency)

            if currency not in unique_billing_currencies:
                raise ValueError(
                    f"Currency {currency} is not used as a billing currency "
                    "for any organization in the database"
                )

            unique_billing_currencies = [currency]

        if account_id is not None:
            logger.info(
                "--account-id is set, generating charge files only for account %s", account_id
            )
            accounts = [account for account in accounts if account.id == account_id]

            if not accounts:
                raise ValueError(f"Account {account_id} not found in the database")

        for currency in unique_billing_currencies:
            for account in accounts:
                await genenerate_monthly_charges(
                    session, currency, account, currency_converter, exports_dir, dry_run
                )


def command(
    ctx: typer.Context,
    exports_dir: Annotated[
        pathlib.Path, typer.Option("--exports-dir", help="Directory to export the charge files to")
    ],
    currency: Annotated[
        str | None,
        typer.Option(
            "--currency",
            help="If set, only generate charge files for this currency",
            show_default=False,
        ),
    ] = None,
    account_id: Annotated[
        str | None,
        typer.Option(
            "--account-id",
            help="If set, only generate charge files for the account with this ID",
            show_default=False,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="If set, only generate charge files but do not upload them to Azure Blob Storage",
            show_default=False,
        ),
    ] = False,
) -> None:
    """
    Generate monthly charge files for the previous month and upload them to Azure Blob Storage.

    By default, the charge files are generated for all accounts and all billing currencies unless
    specified otherwise.
    """
    logger.info("Starting command function")

    if exports_dir.is_file():  # pragma: no cover
        raise ValueError("The exports directory must be a directory, not a file.")

    if not exports_dir.exists():  # pragma: no cover
        logger.info("Exports directory %s does not exist, creating it", str(exports_dir.resolve()))
        exports_dir.mkdir(parents=True)

    asyncio.run(
        main(
            exports_dir=exports_dir,
            currency=currency,
            account_id=account_id,
            dry_run=dry_run,
        )
    )

    logger.info("Completed command function")
