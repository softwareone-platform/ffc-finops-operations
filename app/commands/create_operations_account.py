import asyncio

import typer
from rich import print

from app.conf import Settings
from app.db.base import get_db_engine, get_tx_db_session
from app.db.handlers import AccountHandler
from app.db.models import Account
from app.enums import AccountStatus, AccountType


async def create_operations_account(
    settings: Settings,
    external_id: str,
):
    engine = get_db_engine(settings)
    async with get_tx_db_session(engine) as session:
        account_handler = AccountHandler(session)
        instance = await account_handler.first(
            Account.type == AccountType.OPERATIONS,
            Account.status != AccountStatus.DELETED,
        )
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
            external_id=external_id,
        )
        account = await account_handler.create(account)
        print(
            "[green]The Operations Account has been created: [/green]"
            f"[blue]{account.id} - {account.name}[/blue]."
        )


def command(
    ctx: typer.Context,
    external_id: str = typer.Argument(..., help="Operation Account external ID"),
):
    """
    Create the SoftwareOne Operations Account.
    """
    asyncio.run(create_operations_account(ctx.obj, external_id))
