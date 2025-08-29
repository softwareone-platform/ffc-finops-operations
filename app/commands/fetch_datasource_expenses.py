import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import typer
from fastapi import status
from httpx import HTTPStatusError, ReadTimeout

from app.api_clients.optscale import OptscaleClient
from app.conf import Settings
from app.db.base import session_factory
from app.db.handlers import DatasourceExpenseHandler, OrganizationHandler
from app.db.models import DatasourceExpense, Organization
from app.enums import DatasourceType
from app.notifications import send_exception, send_info
from app.telemetry import capture_telemetry_cli_command

logger = logging.getLogger(__name__)


def filter_relevant_datasources(datasources: list[dict]) -> list[dict]:
    result = []

    for datasource in datasources:
        if datasource["type"] in ["azure_tenant", "gcp_tenant"]:
            logger.warning(
                "Skipping child datasource %s of type %s since it's a child datasource "
                "and its expenses will always be zero",
                datasource["id"],
                datasource["type"],
            )
            continue

        result.append(datasource)

    return result


async def fetch_datasources_for_organizations(
    organizations: Sequence[Organization],
    optscale_client: OptscaleClient,
) -> dict[str, list[dict]]:
    datasources_per_organization_id: dict[str, list[dict]] = {}

    for organization in organizations:
        if organization.linked_organization_id is None:
            logger.warning(
                "Organization %s - %s has no linked organization ID. Skipping...",
                organization.id,
                organization.name,
            )
            continue

        try:
            logger.info("Fetching datasources for organization %s", organization.id)
            response = await optscale_client.fetch_datasources_for_organization(
                organization.linked_organization_id
            )
        except (HTTPStatusError, ReadTimeout) as exc:
            if (
                isinstance(exc, HTTPStatusError)
                and exc.response.status_code == status.HTTP_404_NOT_FOUND
            ):
                msg = f"Organization {organization.id} not found on Optscale."
                logger.warning(msg)
            else:
                msg = (
                    "Unexpected error occurred fetching "
                    f"datasources for organization {organization.id}"
                )
                logger.exception(msg)
                await send_exception("Datasource Expenses Update Error", f"{msg}: {exc}")

            continue

        response_datasources = response.json()["cloud_accounts"]
        logger.info(
            "Fetched %d datasources for organization %s - %s",
            len(response_datasources),
            organization.id,
            organization.name,
        )

        datasources_per_organization_id[organization.id] = filter_relevant_datasources(
            response_datasources
        )

    return datasources_per_organization_id


async def store_datasource_expenses(
    datasource_expense_handler: DatasourceExpenseHandler,
    datasources_per_organization_id: dict[str, list[dict]],
    year: int,
    month: int,
    day: int,
) -> None:
    org_count = 0
    ds_count = 0
    for organization_id, datasources in datasources_per_organization_id.items():
        org_count += 1
        ds_count += len(datasources)
        for datasource in datasources:
            existing_datasource_expense, created = await datasource_expense_handler.get_or_create(
                datasource_id=datasource["account_id"],
                organization_id=organization_id,
                year=year,
                month=month,
                day=day,
                defaults={
                    "expenses": datasource["details"]["cost"],
                    "datasource_name": datasource["name"],
                    "linked_datasource_id": datasource["id"],
                    "linked_datasource_type": datasource["type"],
                },
                extra_conditions=[
                    DatasourceExpense.linked_datasource_type.in_(
                        [DatasourceType.UNKNOWN, datasource["type"]]
                    ),
                ],
            )
            if not created:
                await datasource_expense_handler.update(
                    existing_datasource_expense,
                    {
                        "expenses": datasource["details"]["cost"],
                        "datasource_name": datasource["name"],
                        "linked_datasource_id": datasource["id"],
                        "linked_datasource_type": datasource["type"],
                    },
                )
    msg = (
        f"Expenses of {ds_count} Datasources "
        f"configured by {org_count} Organizations have been updated."
    )
    logger.info(msg)
    await send_info("Datasource Expenses Update Success", msg)


@capture_telemetry_cli_command(__name__, "Update Current Month Datasource Expenses")
async def main(settings: Settings) -> None:
    today = datetime.now(UTC).date()

    async with session_factory() as session:
        datasource_expense_handler = DatasourceExpenseHandler(session)
        organization_handler = OrganizationHandler(session)

        async with session.begin():
            logger.info("Querying organizations with no recent datasource expenses")
            organizations = await organization_handler.query_db()
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
                today.strftime("%d %B %Y"),  # e.g. "March 2025"
            )
            await store_datasource_expenses(
                datasource_expense_handler,
                datasources_per_organization_id,
                year=today.year,
                month=today.month,
                day=today.day,
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
