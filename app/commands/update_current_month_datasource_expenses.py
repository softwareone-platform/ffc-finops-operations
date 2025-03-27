import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import typer
from fastapi import status
from httpx import HTTPStatusError

from app.api_clients.optscale import OptscaleClient
from app.conf import Settings
from app.db.base import session_factory
from app.db.handlers import DatasourceExpenseHandler, OrganizationHandler
from app.db.models import DatasourceExpense, Organization

logger = logging.getLogger(__name__)


async def fetch_datasources_for_organizations(
    organizations: Sequence[Organization],
    optscale_client: OptscaleClient,
) -> dict[str, list[dict]]:
    datasources_per_organization_id: dict[str, list[dict]] = {}

    for organization in organizations:
        if organization.linked_organization_id is None:
            logger.warning(
                "Organization %s has no linked organization ID. Skipping...", organization.id
            )
            continue

        try:
            logger.info("Fetching datasources for organization %s", organization.id)
            response = await optscale_client.fetch_datasources_for_organization(
                organization.linked_organization_id
            )
        except HTTPStatusError as exc:
            response = exc.response

            if exc.response.status_code == status.HTTP_404_NOT_FOUND:
                logger.warning(
                    "Organization %s not found on Optscale. Skipping...", organization.id
                )
            else:
                logger.exception(
                    "Unexpected error occurred fetching datasources for organization %s",
                    organization.id,
                )

            continue

        response_datasources = response.json()["cloud_accounts"]
        logger.info(
            "Fetched %d datasources for organization %s",
            len(response_datasources),
            organization.id,
        )

        datasources_per_organization_id[organization.id] = response_datasources

    return datasources_per_organization_id


async def store_datasource_expenses(
    datasource_expense_handler: DatasourceExpenseHandler,
    datasources_per_organization_id: dict[str, list[dict]],
    year: int,
    month: int,
) -> None:
    for organization_id, datasources in datasources_per_organization_id.items():
        for datasource in datasources:
            existing_datasource_expense, created = await datasource_expense_handler.get_or_create(
                datasource_id=datasource["id"],
                organization_id=organization_id,
                year=year,
                month=month,
                defaults={
                    "month_expenses": datasource["details"]["cost"],
                },
            )
            if not created:
                await datasource_expense_handler.update(
                    existing_datasource_expense,
                    {"month_expenses": datasource["details"]["cost"]},
                )


async def main(settings: Settings) -> None:
    today = datetime.now(UTC).date()

    async with session_factory() as session:
        datasource_expense_handler = DatasourceExpenseHandler(session)
        organization_handler = OrganizationHandler(session)

        async with session.begin():
            logger.info("Querying organizations with no recent datasource expenses")
            organizations = await organization_handler.query_db(
                where_clauses=[
                    ~Organization.datasource_expenses.any(DatasourceExpense.updated_at >= today)
                ],
                unique=True,
            )
            logger.info("Found %d organizations to process", len(organizations))

        async with OptscaleClient(settings) as optscale_client:
            logger.info("Fetching datasources for the organizations to process from Optscale")
            datasources_per_organization_id = await fetch_datasources_for_organizations(
                organizations,
                optscale_client,
            )
            logger.info("Completed fetching datasources for organizations")

        async with session.begin():
            logger.info(
                "Storing datasource expenses for %s organiziations for %s",
                len(organizations),
                today.strftime("%B %Y"),  # e.g. "March 2025"
            )
            await store_datasource_expenses(
                datasource_expense_handler,
                datasources_per_organization_id,
                year=today.year,
                month=today.month,
            )

            logger.info("Completed storing datasource expenses")


def command(ctx: typer.Context) -> None:
    """
    Fetch from Optscale all datasource expenses for the current month
    and store them in the database.
    """
    logger.info("Starting command function")
    asyncio.run(main(ctx.obj))
    logger.info("Completed command function")
