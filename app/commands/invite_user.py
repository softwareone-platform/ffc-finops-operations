import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import typer
from email_validator import EmailNotValidError, validate_email
from rich import print

from app.conf import Settings
from app.db.base import get_db_engine, get_db_session, get_db_sessionmaker
from app.db.handlers import AccountHandler, AccountUserHandler, UserHandler
from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountType, AccountUserStatus, UserStatus


def validate_invited_email(email: str):
    try:
        emailinfo = validate_email(email, check_deliverability=False)
        email = emailinfo.normalized

    except EmailNotValidError as e:
        raise typer.BadParameter(str(e)) from e

    return email


async def get_account(account_handler: AccountHandler, account_id: str | None) -> Account:
    account = None
    if account_id:
        account = await account_handler.first(
            where_clauses=[Account.id == account_id, Account.status == AccountStatus.ACTIVE]
        )
    else:
        account = await account_handler.first(
            where_clauses=[
                Account.type == AccountType.OPERATIONS,
                Account.status == AccountStatus.ACTIVE,
            ]
        )

    if not account:
        if account_id:
            print(f"No Active Account with ID {account_id} has been found.")
        else:
            print("No Active Operations Account has been found.")
        raise typer.Abort()
    return account


async def get_user(user_handler: UserHandler, email: str, name: str) -> User:
    user = await user_handler.first(
        where_clauses=[User.email == email, User.status != UserStatus.DELETED]
    )
    if not user:
        user = User(name=name, email=email, status=UserStatus.DRAFT)
        user = await user_handler.create(user)
    if user.status == UserStatus.DISABLED:
        print(f"The user {email} is disabled.")
        raise typer.Abort()
    return user


async def invite_user(
    settings: Settings, email: str, name: str, account_id: str | None, force: bool = False
):
    """ """
    engine = get_db_engine(settings)
    session_maker = get_db_sessionmaker(engine)

    async with asynccontextmanager(get_db_session)(session_maker) as session:
        account_handler = AccountHandler(session)
        user_handler = UserHandler(session)
        accountuser_handler = AccountUserHandler(session)
        account = await get_account(account_handler, account_id)
        user = await get_user(user_handler, email, name)

        account_user = await accountuser_handler.first(
            where_clauses=[
                AccountUser.account == account,
                AccountUser.user == user,
                AccountUser.status != AccountUserStatus.DELETED,
            ]
        )

        action = "invitation token regenerated successfully!"
        color = "orange3"

        if not account_user:
            account_user = AccountUser(
                account=account,
                user=user,
                status=AccountUserStatus.INVITED,
            )
            action = "invited successfully!"
            color = "green"
        if not force and account_user.id:
            action = "has already been invited!"

            print(f"""
[{color}]User [bold]{user.id} - {user.name} ({user.email})[/bold] {action}[/{color}]

Account: [blue][bold]{account.id}[/bold] - {account.name} ({account.type.value.capitalize()})[/blue]
""")
            return
        account_user.invitation_token = secrets.token_urlsafe(settings.invitation_token_length)
        account_user.invitation_token_expires_at = datetime.now(UTC) + timedelta(
            days=settings.invitation_token_expires_days
        )
        if not account_user.id:
            account_user = await accountuser_handler.create(account_user)
        elif force:  # pragma no branch
            account_user = await accountuser_handler.update(account_user)
        formatted_expires = account_user.invitation_token_expires_at.strftime("%c")  # type: ignore
        print(f"""
[{color}]User [bold]{user.id} - {user.name} ({user.email})[/bold] {action}[/{color}]

Account: [blue][bold]{account.id}[/bold] - {account.name} ({account.type.value.capitalize()})[/blue]
Invitation token: [blue_violet][bold]{account_user.invitation_token}[/bold][/blue_violet]
Expires at: [yellow3]{formatted_expires}[/yellow3]
""")


def command(
    ctx: typer.Context,
    email: str = typer.Argument(..., callback=validate_invited_email),
    name: str = typer.Argument(...),
    account_id: Annotated[
        str | None,
        typer.Option(
            "--account",
            "-a",
            help="Account ID (Default to SoftwareOne Account)",
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force regeneration of the invitation token")
    ] = False,  # noqa: E501
):
    """Invite a User to join an Account."""
    asyncio.run(invite_user(ctx.obj, email, name, account_id, force))
