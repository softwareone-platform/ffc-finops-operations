import asyncio

import typer
from rich.console import Console

from app.conf import Settings
from app.db.base import session_factory
from app.db.handlers import AccountHandler, EntitlementHandler
from app.db.models import Account
from app.enums import AccountStatus, EntitlementStatus

BATCH_SIZE = 100


console = Console(highlighter=None)


async def calculate_accounts_stats(settings: Settings):
    """
    This command calculates the stats about all the entitlements linked to
    all the fetched accounts.
    The Account Model is then updated with the count for each entitlement's status that
    is not DELETED.
    """
    async with session_factory.begin() as session:
        entitlment_handler = EntitlementHandler(session)
        account_handler = AccountHandler(session)

        accounts = await account_handler.query_db(
            where_clauses=[Account.status != AccountStatus.DELETED]
        )
        for account in accounts:
            stats = await entitlment_handler.get_stats_by_account(account.id)
            console.print(
                f"[blue]Fetching accounts: [bold]{account.id} - {account.name}[/bold][/blue]",
            )
            await account_handler.update(
                account,
                data={
                    "new_entitlements_count": stats.get(EntitlementStatus.NEW, 0),
                    "active_entitlements_count": stats.get(EntitlementStatus.ACTIVE, 0),
                    "terminated_entitlements_count": stats.get(EntitlementStatus.TERMINATED, 0),
                },
            )
            console.print(
                f"[blue]Account [bold]{account.id} - {account.name}[/bold][/blue] updated: "
                f"new = {account.new_entitlements_count} active = {account.active_entitlements_count} "  # noqa: E501
                f"terminated = {account.terminated_entitlements_count}"
            )


def command(ctx: typer.Context):
    """
    Update the counters for new, active (redeemed) and terminated entitlements for each Account.
    """
    asyncio.run(calculate_accounts_stats(ctx.obj))
