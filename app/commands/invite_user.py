import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import typer
from email_validator import EmailNotValidError, validate_email
from rich import print
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountType, AccountUserStatus, UserStatus


def validate_invited_email(email: str):
    try:
        emailinfo = validate_email(email, check_deliverability=False)
        email = emailinfo.normalized

    except EmailNotValidError as e:
        raise typer.BadParameter(str(e)) from e

    return email


def get_account(session: Session, account_id: str) -> Account:
    if account_id:
        query = select(Account).where(
            Account.id == account_id, Account.status == AccountStatus.ACTIVE
        )
    else:
        query = select(Account).where(
            Account.type == AccountType.OPERATIONS, Account.status == AccountStatus.ACTIVE
        )
    result = session.execute(query)
    account = result.scalar_one_or_none()
    if not account:
        if account_id:
            print(f"No Active Account with ID {account_id} has been found.")
        else:
            print("No Active Operations Account has been found.")
        raise typer.Abort()
    return account


def get_user(session: Session, email: str, name: str) -> User:
    query = select(User).where(User.email == email, User.status != UserStatus.DELETED)
    result = session.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        user = User(name=name, email=email, status=UserStatus.DRAFT)
        session.add(user)
    if user.status == UserStatus.DISABLED:
        print(f"The user {email} is disabled.")
        raise typer.Abort()
    return user


def get_account_user(session: Session, account: Account, user: User) -> AccountUser | None:
    query = select(AccountUser).where(
        AccountUser.account == account,
        AccountUser.user == user,
        AccountUser.status != AccountUserStatus.DELETED,
    )
    result = session.execute(query)
    return result.scalar_one_or_none()


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
):
    """Invite a User to join an Account."""
    db_engine = create_engine(
        str(ctx.obj.postgres_url),
        echo=ctx.obj.debug,
        future=True,
    )
    SessionMaker = sessionmaker(bind=db_engine)
    with SessionMaker() as session:
        account = get_account(session, account_id)  # type: ignore
        user = get_user(session, email, name)

        account_user = get_account_user(session, account, user)

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

        account_user.invitation_token = secrets.token_urlsafe(ctx.obj.invitation_token_length)
        account_user.invitation_token_expires_at = datetime.now(UTC) + timedelta(
            days=ctx.obj.invitation_token_expires_days
        )

        if not account_user.id:
            session.add(account_user)
        session.commit()
        session.refresh(user)
        session.refresh(account_user)

        print(f"""
[{color}]User [bold]{user.id} - {user.name} ({user.email})[/bold] {action}[/{color}]

Account: [blue][bold]{account.id}[/bold] - {account.name} ({account.type.value.title()})[/blue]
Invitation token: [blue_violet][bold]{account_user.invitation_token}[/bold][/blue_violet]
Expires at: [yellow3]{account_user.invitation_token_expires_at.strftime("%c")}[/yellow3]
""")
