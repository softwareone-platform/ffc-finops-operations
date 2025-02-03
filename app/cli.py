import json
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
import yaml
from fastapi.openapi.utils import get_openapi


class OutputFormat(str, Enum):
    json = "json"
    yaml = "yaml"


app = typer.Typer(
    add_completion=False,
    rich_markup_mode="rich",
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
