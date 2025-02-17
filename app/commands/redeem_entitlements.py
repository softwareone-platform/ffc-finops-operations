from datetime import UTC, datetime

import httpx
import typer
from rich.console import Console
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from app.db.models import Entitlement, Organization
from app.enums import EntitlementStatus, OrganizationStatus

BATCH_SIZE = 100


console = Console(highlighter=None)


def fetch_datasources_for_organization(
    ctx: typer.Context,
    organization_id: str,
) -> dict:
    response = httpx.get(
        f"{ctx.obj.opt_api_base_url}/organizations/{organization_id}/cloud_accounts",
        params={
            "details": "true",
        },
        headers={
            "Secret": ctx.obj.opt_cluster_secret,
        },
    )
    response.raise_for_status()
    return response.json()["cloud_accounts"]


def command(
    ctx: typer.Context,
):
    """Redeem entitlements for an Organization."""
    db_engine = create_engine(
        str(ctx.obj.postgres_url),
        echo=ctx.obj.debug,
        future=True,
    )

    SessionMaker = sessionmaker(bind=db_engine)
    with SessionMaker() as session:
        stmt = (
            select(Organization)
            .where(Organization.status == OrganizationStatus.ACTIVE)
            .order_by(Organization.created_at)
            .execution_options(yield_per=BATCH_SIZE)
        )
        for organization in session.scalars(stmt):
            console.print(
                "[blue]Fetching datasources for organization: "
                f"[bold]{organization.id} - {organization.name}[/bold][/blue]",
            )
            datasources = None
            try:
                datasources = fetch_datasources_for_organization(
                    ctx,
                    organization.operations_external_id,  # type: ignore
                )
            except httpx.HTTPError as e:
                console.print(f"[red]Failed to fetch datasources: {e}[/red]")
                continue
            for datasource in datasources:
                datasource_id = datasource["account_id"]
                match datasource["type"]:
                    case "azure_tenant" | "gcp_tenant":
                        console.print(
                            f"\tFound {datasource["type"]} {datasource['account_id']}, skip it"
                        )
                        continue
                    case "azure_cnr":
                        console.print(
                            f"\t[khaki3]Found Azure CNR {datasource["account_id"]}[/khaki3]"
                        )
                    case "aws_cnr":
                        console.print(
                            f"\t[khaki3]Found AWS CNR {datasource["account_id"]}[/khaki3]"
                        )
                    case "gcp_cnr":
                        console.print(
                            f"\t[khaki3]Found GCP CNR {datasource["account_id"]}[/khaki3]"
                        )
                    case _:
                        console.print(
                            "\t[orange3]Unsupported datasource type "
                            f"{datasource["type"]}, skip it[/orange3]"
                        )
                        continue
                try:
                    query = select(Entitlement).where(
                        Entitlement.datasource_id == datasource_id,
                        Entitlement.status == EntitlementStatus.NEW,
                    )
                    instance = session.scalar(query)
                    if instance:
                        instance.status = EntitlementStatus.ACTIVE
                        instance.redeemed_at = datetime.now(UTC)
                        instance.redeemed_by = organization
                        instance.operations_external_id = datasource["id"]
                        session.add(instance)
                        session.commit()
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
