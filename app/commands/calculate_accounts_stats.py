"""
UPDATE Account SET new_ent_count


SELECT status, count(id) from Entitlement where status != DELETED AND owner_id = account_id
group_by status


UPDATE Account
"""

import asyncio
from contextlib import asynccontextmanager

import typer
from rich.console import Console

from app.conf import Settings
from app.db.base import get_db_engine, get_db_session
from app.db.handlers import AccountHandler, EntitlementHandler
from app.db.models import Account
from app.enums import AccountStatus

BATCH_SIZE = 100


console = Console(highlighter=None)


async def calculate_accounts_stats(settings: Settings):
    engine = get_db_engine(settings)
    # stmt = select(
    #     Account,
    #     func.count().over(partition_by=Account.status).label("id")
    # ).where(Account.status != AccountStatus.DELETED, Entitlement.owner_id == Account.id)
    #
    async with asynccontextmanager(get_db_session)(engine) as session:
        entitlment_handler = EntitlementHandler(session)
        account_handler = AccountHandler(session)

        accounts = await account_handler.query_db(
            where_clauses=[Account.status != AccountStatus.DELETED]
        )
        for account in accounts:
            # print("account:", account.id, account.status, account.type)
            response = await entitlment_handler.get_stats_by_account(account.id)
            print("enti:", response)
            console.print(
                "[blue]Fetching accounts: " f"[bold]{account.id} - {account.name}[/bold][/blue]",
            )
        # async for account in account_hander.stream_scalars(stmt
        # ):
        #     console.print(
        #         "[blue]Fetching accounts: "
        #         f"[bold]{account.id} - {account.name}[/bold][/blue]",
        #     )


def command(
    ctx: typer.Context,
):
    asyncio.run(calculate_accounts_stats(ctx.obj))
