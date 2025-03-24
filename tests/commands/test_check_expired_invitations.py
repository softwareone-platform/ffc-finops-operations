from datetime import UTC, datetime, timedelta

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.commands.check_expired_invitations import check_expired_invitations
from app.conf import Settings
from app.db.models import Account, AccountUser, User
from app.enums import AccountUserStatus, UserStatus
from tests.types import ModelFactory


@pytest.fixture(autouse=True)
def mock_db_session(db_session: AsyncSession, mocker: MockerFixture):
    async def mock_get_db_session(*args, **kwargs):  # noqa: RUF029
        yield db_session

    mocker.patch("app.commands.check_expired_invitations.get_db_session", new=mock_get_db_session)


async def test_check_expired_invitation(
    test_settings: Settings,
    db_session: AsyncSession,
    operations_account: Account,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    capsys: pytest.CaptureFixture,
):
    user = await user_factory(
        name="Peter Parker",
        email="peter.parker@spiderman.com",
        status=UserStatus.ACTIVE,
    )
    active = await accountuser_factory(
        account_id=operations_account.id,
        user_id=user.id,
        status=AccountUserStatus.ACTIVE,
        invitation_token_expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    deleted = await accountuser_factory(
        account_id=operations_account.id,
        user_id=user.id,
        status=AccountUserStatus.DELETED,
        invitation_token_expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    invitation_expired = await accountuser_factory(
        account_id=operations_account.id,
        user_id=user.id,
        status=AccountUserStatus.INVITATION_EXPIRED,
        invitation_token_expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    expired_invited_1 = await accountuser_factory(
        account_id=operations_account.id,
        user_id=user.id,
        status=AccountUserStatus.INVITED,
        invitation_token_expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    expired_invited_2 = await accountuser_factory(
        account_id=operations_account.id,
        user_id=user.id,
        status=AccountUserStatus.INVITED,
        invitation_token_expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    await check_expired_invitations(test_settings)

    captured = capsys.readouterr()
    assert "2 invitations" in captured.out

    await db_session.refresh(active)
    assert active.status == AccountUserStatus.ACTIVE

    await db_session.refresh(deleted)
    assert deleted.status == AccountUserStatus.DELETED

    await db_session.refresh(invitation_expired)
    assert invitation_expired.status == AccountUserStatus.INVITATION_EXPIRED

    await db_session.refresh(expired_invited_1)
    assert expired_invited_1.status == AccountUserStatus.INVITATION_EXPIRED

    await db_session.refresh(expired_invited_2)
    assert expired_invited_2.status == AccountUserStatus.INVITATION_EXPIRED


def test_invite_user_command(
    mocker: MockerFixture,
    test_settings: Settings,
):
    mocker.patch("app.cli.get_settings", return_value=test_settings)
    mock_check_coro = mocker.MagicMock()
    mock_check = mocker.MagicMock(return_value=mock_check_coro)

    mocker.patch("app.commands.check_expired_invitations.check_expired_invitations", mock_check)
    mock_run = mocker.patch("app.commands.invite_user.asyncio.run")
    runner = CliRunner()

    result = runner.invoke(app, ["check-expired-invitations"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(mock_check_coro)

    mock_check.assert_called_once_with(test_settings)
