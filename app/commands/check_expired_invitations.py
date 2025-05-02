import asyncio
import logging
from datetime import UTC, datetime

import typer
from sqlalchemy import update

from app.conf import Settings
from app.db.base import session_factory
from app.db.models import AccountUser
from app.enums import AccountUserStatus

logger = logging.getLogger(__name__)


async def check_expired_invitations(settings: Settings):
    async with session_factory.begin() as session:
        stmt = (
            update(AccountUser)
            .where(
                AccountUser.status == AccountUserStatus.INVITED,
                AccountUser.invitation_token_expires_at < datetime.now(UTC),
            )
            .values(status=AccountUserStatus.INVITATION_EXPIRED)
        )

        result = await session.execute(stmt)

        logger.info(
            f"{result.rowcount} invitations have been "
            "successfully transitioned to `invitation-expired`.",
        )


def command(ctx: typer.Context):
    """Transition expired invitations to the `invitation-expired` status."""
    asyncio.run(check_expired_invitations(ctx.obj))
