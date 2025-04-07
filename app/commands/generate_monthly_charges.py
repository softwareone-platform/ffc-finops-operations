import asyncio
import csv
import logging
from collections.abc import Sequence
from copy import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import IO, Self

import typer
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session

from app.conf import get_settings
from app.currency import CurrencyConverter
from app.db.handlers import (
    DatasourceExpenseHandler,
    OrganizationHandler,
)
from app.db.models import Account, DatasourceExpense, Entitlement, Organization
from app.enums import AccountType, EntitlementStatus, OrganizationStatus

logger = logging.getLogger(__name__)

# TODO: Use excel instead of csv


@dataclass
class ChargeEntry:
    subscription_search_criteria: str
    subscription_search_value: str
    item_search_criteria: str
    item_search_value: str
    usage_start_time: datetime
    usage_end_time: datetime
    price: Decimal
    external_reference: str
    vendor_description_1: str
    vendor_description_2: str
    vendor_reference: str

    @classmethod
    def from_datasource_expense(cls, exp: DatasourceExpense) -> Self:
        settings = get_settings()

        if exp.organization.linked_organization_id is None:
            raise ValueError(
                f"Cannot generate charge for datasource expense {exp.id}: "
                f"Organization {exp.organization.id} does not have a linked organization ID."
            )

        month_start = datetime(exp.year, exp.month, 1)
        month_end = month_start + relativedelta(day=31)
        price = exp.month_expenses * Decimal(settings.billing_percentage) / 100

        return cls(
            subscription_search_criteria="subscription.externalIds.vendor",
            subscription_search_value=exp.organization_id,
            item_search_criteria="item.externalIds.vendor",
            item_search_value=exp.id,  # TODO: Pretty sure this is not the correct value
            usage_start_time=month_start,
            usage_end_time=month_end,
            price=price,
            external_reference=exp.organization.linked_organization_id,
            vendor_description_1=exp.datasource_name,
            vendor_description_2=exp.datasource_id,
            vendor_reference="",
        )

    def contra_entry(self, entitlement: Entitlement) -> Self:
        contra_entry = copy(self)
        # TODO: Pretty sure this is not the correct value
        contra_entry.item_search_value = entitlement.id
        contra_entry.price = -self.price

        return contra_entry


@dataclass
class ChargesFileGenerator:
    account: Account
    currency: str
    currency_converter: CurrencyConverter

    async def fetch_datasource_expenses(self) -> Sequence[DatasourceExpense]:
        today = datetime.now(UTC).date()
        last_month = today - relativedelta(months=1)

        session = async_object_session(self.account)

        if session is None:
            # This can happen if we only create an account python object but we haven't yet
            # added it to the database. If that's the case, that's incrrect usage of the class,
            # so we should raise an error.

            raise ValueError(
                "Account must be associated with a session to fetch datasource expenses."
            )

        organization_handler = OrganizationHandler(session)
        datasource_expense_handler = DatasourceExpenseHandler(session)

        logger.info(
            "Querying organizations to process for account %s and currency %s",
            self.account.id,
            self.currency,
        )

        currency_filter = (
            Organization.currency == self.currency
            if self.account.type == AccountType.AFFILIATE
            else Organization.billing_currency == self.currency
        )

        organizations = await organization_handler.query_db(
            # TODO: What is the organization was deleted after the last billing period
            #       but before the the current one? Maybe this filter should never be applied?
            # TODO: What about cancelled status?
            where_clauses=[Organization.status != OrganizationStatus.DELETED, currency_filter],
        )
        logger.info("Found %d organizations to process", len(organizations))

        for organization in organizations:
            logger.info(
                "Querying datasource expenses for organization %s for month = %s, year = %s",
                organization.id,
                last_month.month,
                last_month.year,
            )
            org_expenses = await datasource_expense_handler.query_db(
                where_clauses=[
                    DatasourceExpense.organization == organization,
                    DatasourceExpense.month == last_month.month,
                    DatasourceExpense.year == last_month.year,
                ],
                unique=True,
            )
            logger.info(
                "Found %d datasource expenses for organization %s for month = %s, year = %s",
                len(org_expenses),
                organization.id,
                last_month.month,
                last_month.year,
            )

        return org_expenses

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
        entry = ChargeEntry.from_datasource_expense(datasource_expense)

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
            charge_entries = []

            entry.price = self.currency_converter.convert_currency(
                entry.price,
                from_currency=datasource_expense.organization.currency,
                to_currency=datasource_expense.organization.billing_currency,
            )
            charge_entries.append(entry)

            for entitlement in datasource_expense.entitlements:
                if entitlement.status != EntitlementStatus.ACTIVE:
                    continue

                charge_entries.append(entry.contra_entry(entitlement))

                # If multiple entitlements match the same datasource expense, we need to
                # add only the contra entry for the first one (the entitlements are
                # already ordered by created_at)
                break

            return charge_entries

        # pragma: no cover
        raise ValueError(f"Unknown account type: {self.account.type}")

    async def generate_charges_file(self, file: IO) -> bool:
        datasource_expenses = await self.fetch_datasource_expenses()
        charge_entries = self.get_charge_entries(datasource_expenses)

        if not charge_entries:
            return False  # not creating an empty file

        # TODO: Create the db record for the generated file with DRAFT status

        dict_writer = csv.DictWriter(
            file,
            fieldnames=[
                "Entry ID",
                "Subscription Search Criteria",
                "Subscription Search Value",
                "Item Search Criteria",
                "Item Search Value",
                "Usage Start Time",
                "Usage End Time",
                "Quantity",
                "Purchase Price",
                "Total Purchase Price",
                "External Reference",
                "Vendor Description 1",
                "Vendor Description 2",
                "Vendor Reference",
            ],
            lineterminator="\n",
        )

        dict_writer.writeheader()

        for row_num, entry in enumerate(charge_entries, start=1):
            dict_writer.writerow(
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
            )

        return True


async def fetch_account_currencies(session: AsyncSession, account: Account) -> Sequence[str]:
    """Fetch unique currencies from the database."""

    logger.info(
        "Fetching unique currencies for account %s of type %s",
        account.id,
        account.type,
    )

    if account.type == AccountType.AFFILIATE:
        logger.info("Account is of type AFFILIATE, using Organization.currency")
        currencies_stmt = select(Organization.currency).distinct()
    elif account.type == AccountType.OPERATIONS:
        logger.info("Account is of type OPERATIONS, using Organization.billing_currency")
        currencies_stmt = select(Organization.billing_currency).distinct()
    else:  # pragma: no cover
        raise ValueError(f"Unknown account type: {account.type}")

    currencies = (await session.scalars(currencies_stmt)).all()

    logger.info(
        "Found the following currencies for account %s of type %s: %s",
        account.id,
        account.type,
        ", ".join(currencies),
    )
    return currencies


def command(ctx: typer.Context) -> None:
    """
    Delete all datasource expenses older than 6 months from the database.
    """
    logger.info("Starting command function")
    asyncio.run(main(ctx.obj))
    logger.info("Completed command function")
