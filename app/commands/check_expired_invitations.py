import asyncio
from datetime import UTC, datetime

import typer
from rich import print
from sqlalchemy import update

from app.conf import Settings
from app.db.base import get_db_engine, get_tx_db_session
from app.db.models import AccountUser
from app.enums import AccountUserStatus


async def check_expired_invitations(settings: Settings):
    engine = get_db_engine(settings)
    async with get_tx_db_session(engine) as session:
        stmt = (
            update(AccountUser)
            .where(
                AccountUser.status == AccountUserStatus.INVITED,
                AccountUser.invitation_token_expires_at < datetime.now(UTC),
            )
            .values(status=AccountUserStatus.INVITATION_EXPIRED)
        )

        result = await session.execute(stmt)

        print(
            f"[green][bold]{result.rowcount}[/bold] "
            "invitations have been successfully transitioned to `invitation-expired`.[/]",
        )


def command(ctx: typer.Context):
    """Transition expired invitations to the `invitation-expired` status."""
    asyncio.run(check_expired_invitations(ctx.obj))
