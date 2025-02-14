import asyncio
import shlex
from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app import settings
from app.cli import app
from app.db.handlers import AccountUserHandler, UserHandler
from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountUserStatus, UserStatus
from tests.types import ModelFactory


@freeze_time("2025-03-07T10:00:00Z")
async def test_invite_user(db_session: AsyncSession, operations_account: Account):
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        shlex.split('invite-user test@example.com "Test User"'),
    )
    assert result.exit_code == 0

    assert "invited successfully" in result.stdout

    user_handler = UserHandler(db_session)
    user = await user_handler.first(
        User.email == "test@example.com",
    )
    assert user is not None
    assert user.status == UserStatus.DRAFT
    assert user.name == "Test User"
    accountuser_handler = AccountUserHandler(db_session)
    account_user = await accountuser_handler.get_account_user(operations_account.id, user.id)
    assert account_user is not None
    assert account_user.status == AccountUserStatus.INVITED
    assert account_user.invitation_token is not None
    assert account_user.invitation_token_expires_at == (
        datetime.now(UTC) + timedelta(days=settings.invitation_token_expires_days)
    )


@freeze_time("2025-03-07T10:00:00Z")
async def test_invite_user_already_invited(
    db_session: AsyncSession,
    operations_account: Account,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
):
    user = await user_factory(
        email="test@example.com",
        name="Test User",
        status=UserStatus.DRAFT,
    )
    account_user = await accountuser_factory(
        user_id=user.id,
        account_id=operations_account.id,
        status=AccountUserStatus.INVITED,
        invitation_token="an invitation token",
        invitation_token_expires_at=datetime(2025, 3, 7, 9, 0, 0, tzinfo=UTC),
    )

    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        shlex.split('invite-user test@example.com "Test User"'),
    )
    assert result.exit_code == 0
    assert "invitation token regenerated successfully" in result.stdout

    db_session.expunge_all()

    user_handler = UserHandler(db_session)
    db_user = await user_handler.first(
        User.email == "test@example.com",
    )
    assert db_user is not None
    assert db_user.status == UserStatus.DRAFT
    assert db_user.name == "Test User"
    accountuser_handler = AccountUserHandler(db_session)
    db_account_user = await accountuser_handler.get_account_user(operations_account.id, user.id)
    assert db_account_user is not None
    assert db_account_user.status == AccountUserStatus.INVITED
    assert db_account_user.invitation_token != account_user.invitation_token
    assert db_account_user.invitation_token_expires_at != account_user.invitation_token_expires_at
    assert db_account_user.invitation_token_expires_at == (
        datetime.now(UTC) + timedelta(days=settings.invitation_token_expires_days)
    )


def test_invite_user_invalid_email():
    runner = CliRunner()
    result = runner.invoke(app, shlex.split("invite-user invalid-email UserName"))
    assert result.exit_code != 0
    assert "Invalid value for 'EMAIL'" in result.stdout


async def test_invite_user_user_disabled(
    user_factory: ModelFactory[User],
    operations_account: Account,
):
    await user_factory(
        email="test@example.com",
        name="Test User",
        status=UserStatus.DISABLED,
    )

    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        shlex.split('invite-user test@example.com "Test User"'),
    )
    assert result.exit_code != 0
    assert "The user test@example.com is disabled." in result.stdout


@freeze_time("2025-03-07T10:00:00Z")
async def test_invite_user_non_default_account(
    db_session: AsyncSession, account_factory: ModelFactory[Account]
):
    account = await account_factory()
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        shlex.split(f'invite-user --account {account.id} test@example.com "Test User"'),
    )
    assert result.exit_code == 0

    assert "invited successfully" in result.stdout

    user_handler = UserHandler(db_session)
    user = await user_handler.first(
        User.email == "test@example.com",
    )
    assert user is not None
    assert user.status == UserStatus.DRAFT
    assert user.name == "Test User"
    accountuser_handler = AccountUserHandler(db_session)
    account_user = await accountuser_handler.get_account_user(account.id, user.id)
    assert account_user is not None
    assert account_user.status == AccountUserStatus.INVITED
    assert account_user.invitation_token is not None
    assert account_user.invitation_token_expires_at == (
        datetime.now(UTC) + timedelta(days=settings.invitation_token_expires_days)
    )


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.DELETED, AccountStatus.DISABLED],
)
async def test_invite_user_non_default_account_not_active(
    db_session: AsyncSession,
    account_factory: ModelFactory[Account],
    account_status: AccountStatus,
):
    account = await account_factory(status=account_status)
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        shlex.split(f'invite-user --account {account.id} test@example.com "Test User"'),
    )
    assert result.exit_code != 0
    assert f"No Active Account with ID {account.id} has been found." in result.stdout


def test_invite_user_no_operations_account():
    runner = CliRunner()
    result = runner.invoke(
        app,
        shlex.split('invite-user test@example.com "Test User"'),
    )
    assert result.exit_code != 0
    assert "No Active Operations Account has been found." in result.stdout
