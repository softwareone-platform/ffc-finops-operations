import inspect

import typer

from app import commands

app = typer.Typer(
    help="FinOps for Cloud Operations API Command Line Interface",
    add_completion=False,
    rich_markup_mode="rich",
)


for name, module in inspect.getmembers(commands):
    if not inspect.ismodule(module):
        continue

    if hasattr(module, "command"):
        app.command(name=name.replace("_", "-"))(module.command)


@app.callback()
def main(
    ctx: typer.Context,
):
    from app import settings

    ctx.obj = settings
