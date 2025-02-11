import asyncio
import json
import shlex
from pathlib import Path

import yaml
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.db.handlers import AccountHandler
from app.db.models import Account
from app.enums import AccountStatus, AccountType


def test_openapi(mocker: MockerFixture):
    spec = {"test": "openapi"}
    mocker.patch("app.cli.get_openapi", return_value=spec)
    mocked_open = mocker.mock_open()
    mocker.patch("app.cli.open", mocked_open)

    runner = CliRunner()
    result = runner.invoke(app, "openapi")

    assert result.exit_code == 0
    mocked_open.assert_called_once_with(Path("ffc_operations_openapi_spec.yml"), "w")
    written_data = "".join(call.args[0] for call in mocked_open().write.call_args_list)
    assert written_data == yaml.dump(spec, indent=2)


def test_openapi_custom_output(mocker: MockerFixture):
    spec = {"test": "openapi"}
    mocker.patch("app.cli.get_openapi", return_value=spec)
    mocked_open = mocker.mock_open()
    mocker.patch("app.cli.open", mocked_open)

    runner = CliRunner()
    result = runner.invoke(app, shlex.split("openapi -o openapi.json -f json"))

    assert result.exit_code == 0
    mocked_open.assert_called_once_with(Path("openapi.json"), "w")
    written_data = "".join(call.args[0] for call in mocked_open().write.call_args_list)
    assert written_data == json.dumps(spec, indent=2)


async def test_create_op_account(db_session: AsyncSession):
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(None, runner.invoke, app, ["create-op-account"])
    assert result.exit_code == 0
    assert "The Operations Account has been created" in result.stdout
    account_handler = AccountHandler(db_session)
    assert (
        await account_handler.count(
            Account.type == AccountType.OPERATIONS, Account.status == AccountStatus.ACTIVE
        )
        == 1
    )


async def test_create_op_account_exixt(db_session: AsyncSession):
    account_handler = AccountHandler(db_session)
    account = await account_handler.create(
        Account(name="SWO", type=AccountType.OPERATIONS, status=AccountStatus.ACTIVE)
    )
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(None, runner.invoke, app, ["create-op-account"])
    assert result.exit_code == 0
    assert "The Operations Account already exist" in result.stdout
    assert f"{account.id} - {account.name}" in result.stdout
    assert (
        await account_handler.count(
            Account.type == AccountType.OPERATIONS, Account.status == AccountStatus.ACTIVE
        )
        == 1
    )
