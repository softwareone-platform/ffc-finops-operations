import asyncio
import shlex

from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.db.handlers import AccountHandler
from app.db.models import Account
from app.enums import AccountStatus, AccountType


async def test_create_op_account(db_session: AsyncSession):
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None, runner.invoke, app, shlex.split("create-operations-account ACC-1234-5678")
    )
    assert result.exit_code == 0
    assert "The Operations Account has been created" in result.stdout
    account_handler = AccountHandler(db_session)
    assert (
        await account_handler.count(
            Account.type == AccountType.OPERATIONS,
            Account.status == AccountStatus.ACTIVE,
            Account.external_id == "ACC-1234-5678",
        )
        == 1
    )


async def test_create_op_account_exist(db_session: AsyncSession):
    account_handler = AccountHandler(db_session)
    account = await account_handler.create(
        Account(
            name="SWO",
            type=AccountType.OPERATIONS,
            status=AccountStatus.ACTIVE,
            external_id="ACC-1234-5678",
        )
    )
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None, runner.invoke, app, shlex.split("create-operations-account ACC-1234-5678")
    )
    assert result.exit_code == 0
    assert "The Operations Account already exist" in result.stdout
    assert f"{account.id} - {account.name}" in result.stdout
    assert (
        await account_handler.count(
            Account.type == AccountType.OPERATIONS, Account.status == AccountStatus.ACTIVE
        )
        == 1
    )
