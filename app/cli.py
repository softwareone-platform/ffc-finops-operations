import json
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
import yaml
from fastapi.openapi.utils import get_openapi
from rich import print
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import settings
from app.db.models import Account
from app.enums import AccountStatus, AccountType


class OutputFormat(str, Enum):
    json = "json"
    yaml = "yaml"


app = typer.Typer(
    add_completion=False,
    rich_markup_mode="rich",
)


@app.command()
def create_op_account():
    """
    Create the SoftwareOne Operations Account.
    """
    db_engine = create_engine(
        str(settings.postgres_url),
        echo=settings.debug,
        future=True,
    )
    session = sessionmaker(bind=db_engine)
    with session() as session:
        query = select(Account).where(
            Account.type == AccountType.OPERATIONS, Account.status != AccountStatus.DELETED
        )
        result = session.execute(query)
        instance = result.scalar_one_or_none()
        if instance:
            print(
                "[orange3]The Operations Account already exist: [/orange3]"
                f"[blue]{instance.id} - {instance.name}[/blue]."
            )
            return

        account = Account(
            name="SoftwareOne",
            type=AccountType.OPERATIONS,
            status=AccountStatus.ACTIVE,
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        print(
            "[green]The Operations Account has been created: [/green]"
            f"[blue]{account.id} - {account.name}[/blue]."
        )


@app.command()
def openapi(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file",
        ),
    ] = Path("ffc_operations_openapi_spec.yml"),
    output_format: Annotated[
        OutputFormat,
        typer.Option(
            "--output-format",
            "-f",
            help="Output file format",
        ),
    ] = OutputFormat.yaml,
):
    """
    Generates the OpenAPI spec file.
    """
    from app import main

    dump_fn = json.dump if output_format == OutputFormat.json else yaml.dump
    spec = get_openapi(
        title=main.app.title,
        version=main.app.version,
        openapi_version=main.app.openapi_version,
        description=main.app.description,
        tags=main.app.openapi_tags,
        routes=main.app.routes,
    )
    with open(output, "w") as f:  # type: ignore
        dump_fn(spec, f, indent=2)


@app.callback()
def main(
    ctx: typer.Context,
):
    from app import settings

    ctx.obj = settings
