import asyncio
import logging
from datetime import UTC, date, datetime

import typer
from fastapi import status
from httpx import HTTPStatusError

from app.api_clients.optscale import OptscaleClient
from app.conf import Settings
from app.db.base import session_factory
from app.db.handlers import DatasourceExpenseHandler, OrganizationHandler
from app.db.models import DatasourceExpense, Organization
from app.enums import DatasourceType
from app.notifications import send_exception, send_info
from app.telemetry import capture_telemetry

logger = logging.getLogger(__name__)


def filter_relevant_datasources(datasources: list[dict]) -> list[dict]:
    result = []

    for datasource in datasources:
        if datasource["type"] in ["azure_tenant", "gcp_tenant"]:
            logger.warning(
                f"Skipping child datasource {datasource['id']} of type {datasource['type']} "
                "since it's a child datasource and its expenses will always be zero",
            )
            continue

        result.append(datasource)

    return result


async def process_datasources_for_organization(
    organization: Organization,
    optscale_client: OptscaleClient,
    semaphore: asyncio.Semaphore,
    today: date,
) -> int:
    async with semaphore:
        try:
            logger.info(f"Fetching datasources for organization {organization.id}")
            response = await optscale_client.fetch_datasources_for_organization(
                organization.linked_organization_id,
            )
            response_datasources = response.json()["cloud_accounts"]
            logger.info(
                f"Fetched {len(response_datasources)} datasources for "
                f"organization {organization.id} - {organization.name}"
            )
            filtered_datasources = filter_relevant_datasources(response_datasources)

            await store_datasource_expenses(
                organization.id,
                filtered_datasources,
                year=today.year,
                month=today.month,
                day=today.day,
            )

            return len(filtered_datasources)
        except HTTPStatusError as exc:
            if exc.response.status_code == status.HTTP_404_NOT_FOUND:
                msg = f"Organization {organization.id} not found on Optscale."
                logger.warning(msg)
            else:
                msg = (
                    "Unexpected error occurred fetching "
                    f"datasources for organization {organization.id}"
                )
                logger.exception(msg)
                await send_exception("Datasource Expenses Update Error", f"{msg}: {exc}")
            return 0


async def store_datasource_expenses(
    organization_id: str,
    datasources: list[dict],
    year: int,
    month: int,
    day: int,
):
    async with session_factory() as session:
        datasource_handler = DatasourceExpenseHandler(session)
        async with session.begin():
            for datasource in datasources:
                existing_datasource_expense, created = await datasource_handler.get_or_create(
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
                    await datasource_handler.update(
                        existing_datasource_expense,
                        {
                            "expenses": datasource["details"]["cost"],
                            "datasource_name": datasource["name"],
                            "linked_datasource_id": datasource["id"],
                            "linked_datasource_type": datasource["type"],
                        },
                    )

    logger.info(f"Stored {len(datasources)} datasource expenses for organization {organization_id}")


@capture_telemetry(__name__, "Update Current Month Datasource Expenses")
async def main(settings: Settings) -> None:
    today = datetime.now(UTC).date()

    async with session_factory() as session:
        organization_handler = OrganizationHandler(session)
        async with session.begin():
            logger.info("Querying organizations")
            organizations = await organization_handler.query_db()
            logger.info(f"Found {len(organizations)} organizations to process")

    logger.info("Fetching datasources for the organizations to process from Optscale")
    optscale_client = OptscaleClient(settings)
    semaphore = asyncio.Semaphore(settings.max_parallel_tasks)
    tasks = []

    for organization in organizations:
        if organization.linked_organization_id is None:
            logger.warning(
                f"Organization {organization.id} - {organization.name} "
                f"has no linked organization ID. Skipping...",
            )
            continue

        tasks.append(
            asyncio.create_task(
                process_datasources_for_organization(
                    organization,
                    optscale_client,
                    semaphore,
                    today,
                )
            )
        )

    results = await asyncio.gather(*tasks)
    msg = (
        f"Expenses of {sum(results)} Datasources "
        f"configured by {len(results)} Organizations have been updated."
    )
    logger.info(msg)
    await send_info("Datasource Expenses Update Success", msg)


def command(ctx: typer.Context) -> None:
    """
    Fetch from Optscale all datasource expenses for the current month
    and store them in the database.
    """
    logger.info("Starting command function")
    asyncio.run(main(ctx.obj))
    logger.info("Completed command function")
