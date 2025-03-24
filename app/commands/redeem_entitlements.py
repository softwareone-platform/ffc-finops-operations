import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import typer
from rich.console import Console
from sqlalchemy.exc import DatabaseError

from app.api_clients.optscale import OptscaleClient
from app.conf import Settings
from app.db.base import get_db_engine, get_db_session, get_db_sessionmaker
from app.db.handlers import EntitlementHandler, OrganizationHandler
from app.db.models import Entitlement, Organization
from app.enums import EntitlementStatus, OrganizationStatus

BATCH_SIZE = 100


console = Console(highlighter=None)


async def fetch_datasources_for_organization(
    settings: Settings,
    organization_id: str,
) -> dict:
    client = OptscaleClient(settings)
    response = await client.fetch_datasources_for_organization(organization_id)
    return response.json()["cloud_accounts"]


async def redeem_entitlements(
    settings: Settings,
):
    engine = get_db_engine(settings)
    session_maker = get_db_sessionmaker(engine)
    async with asynccontextmanager(get_db_session)(session_maker) as session:
        organization_handler = OrganizationHandler(session)
        entitlement_handler = EntitlementHandler(session)

        async for organization in organization_handler.stream_scalars(
            extra_conditions=[Organization.status == OrganizationStatus.ACTIVE],
            order_by=[Organization.created_at],
            batch_size=BATCH_SIZE,
        ):
            console.print(
                "[blue]Fetching datasources for organization: "
                f"[bold]{organization.id} - {organization.name}[/bold][/blue]",
            )
            datasources = None
            try:
                datasources = await fetch_datasources_for_organization(
                    settings,
                    organization.linked_organization_id,  # type: ignore
                )
            except httpx.HTTPError as e:
                console.print(f"[red]Failed to fetch datasources: {e}[/red]")
                continue
            for datasource in datasources:
                datasource_id = datasource["account_id"]
                match datasource["type"]:
                    case "azure_tenant" | "gcp_tenant":
                        console.print(
                            f"\tFound {datasource['type']} {datasource['account_id']}, skip it"
                        )
                        continue
                    case "azure_cnr":
                        console.print(
                            f"\t[khaki3]Found Azure CNR {datasource['account_id']}[/khaki3]"
                        )
                    case "aws_cnr":
                        console.print(
                            f"\t[khaki3]Found AWS CNR {datasource['account_id']}[/khaki3]"
                        )
                    case "gcp_cnr":
                        console.print(
                            f"\t[khaki3]Found GCP CNR {datasource['account_id']}[/khaki3]"
                        )
                    case _:
                        console.print(
                            "\t[orange3]Unsupported datasource type "
                            f"{datasource['type']}, skip it[/orange3]"
                        )
                        continue
                try:
                    instance = await entitlement_handler.first(
                        where_clauses=[
                            Entitlement.datasource_id == datasource_id,
                            Entitlement.status == EntitlementStatus.NEW,
                        ]
                    )
                    if instance:
                        await entitlement_handler.update(
                            instance,
                            data={
                                "status": EntitlementStatus.ACTIVE,
                                "redeemed_at": datetime.now(UTC),
                                "redeemed_by": organization,
                                "linked_datasource_id": datasource["id"],
                                "linked_datasource_type": datasource["type"],
                                "linked_datasource_name": datasource["name"],
                            },
                        )
                        console.print(
                            f"\t\t[green]Entitlement {instance.id} for datasource {datasource_id} "
                            "has been redeemed successfully![/green]"
                        )
                    else:
                        console.print(
                            "\t\t[magenta]No Entitlement in NEW status has been found for "
                            f"datasource {datasource_id}[/magenta]"
                        )

                except DatabaseError as e:  # pragma: no cover
                    console.print(f"[red]An error with the database occurred: {e}[/red]")
                    continue


def command(
    ctx: typer.Context,
):
    """Redeem entitlements for an Organization."""
    asyncio.run(redeem_entitlements(ctx.obj))
