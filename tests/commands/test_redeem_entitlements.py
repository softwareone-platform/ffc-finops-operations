from datetime import UTC, datetime

import pytest
from freezegun import freeze_time
from httpx import HTTPStatusError, ReadTimeout
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.commands.redeem_entitlements import fetch_datasources_for_organization, redeem_entitlements
from app.conf import Settings
from app.db.models import Entitlement, Organization
from app.enums import DatasourceType, EntitlementStatus


@freeze_time("2025-03-07T10:00:00Z")
async def test_redeeem_entitlements(
    mocker: MockerFixture,
    test_settings: Settings,
    db_session: AsyncSession,
    apple_inc_organization: Organization,
    entitlement_aws: Entitlement,
):
    mocker.patch(
        "app.commands.redeem_entitlements.fetch_datasources_for_organization",
        return_value=[
            {
                "id": "ds1",
                "name": "aws ds",
                "type": "aws_cnr",
                "account_id": entitlement_aws.datasource_id,
            },
            {
                "id": "ds2",
                "name": "azure ds",
                "type": "azure_cnr",
                "account_id": "azure-account-id",
            },
            {"id": "ds3", "name": "gcp ds", "type": "gcp_cnr", "account_id": "gcp-account-id"},
            {
                "id": "ds4",
                "name": "aws tenant ds",
                "type": "aws_tenant",
                "account_id": "aws-tentant-id",
            },
            {
                "id": "ds5",
                "name": "azure tenant ds",
                "type": "azure_tenant",
                "account_id": "azure-tentant-id",
            },
            {
                "id": "ds",
                "name": "gcp tenant ds",
                "type": "gcp_tenant",
                "account_id": "gcp-tentant-id",
            },
        ],
    )

    await redeem_entitlements(test_settings)

    await db_session.refresh(entitlement_aws)
    assert entitlement_aws.linked_datasource_id == "ds1"
    assert entitlement_aws.linked_datasource_name == "aws ds"
    assert entitlement_aws.linked_datasource_type == DatasourceType.AWS_CNR
    assert entitlement_aws.status == EntitlementStatus.ACTIVE
    assert entitlement_aws.redeemed_by == apple_inc_organization
    assert entitlement_aws.redeemed_at is not None
    assert entitlement_aws.redeemed_at == datetime.now(UTC)


async def test_redeeem_entitlements_error_fetching_datasources(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture,
    test_settings: Settings,
    apple_inc_organization: Organization,
    entitlement_aws: Entitlement,
    db_session: AsyncSession,
):
    mocker.patch(
        "app.commands.redeem_entitlements.fetch_datasources_for_organization",
        side_effect=ReadTimeout("timed out"),
    )
    await redeem_entitlements(test_settings)
    captured = capsys.readouterr()
    assert "Failed to fetch datasources: timed out" in captured.out
    await db_session.refresh(entitlement_aws)
    assert entitlement_aws.status == EntitlementStatus.NEW
    assert entitlement_aws.redeemed_by is None


async def test_fetch_datasources_for_organization(
    test_settings: Settings,
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
):
    datasources = [
        {"id": "ds1", "type": "aws_cnr", "account_id": "aws-account-id"},
    ]
    httpx_mock.add_response(
        method="GET",
        url=f"{test_settings.opt_api_base_url}/organizations/linked_organization_id/cloud_accounts?details=true",
        match_headers={"Secret": test_settings.opt_cluster_secret},
        json={
            "cloud_accounts": datasources,
        },
    )

    fetched_datasources = await fetch_datasources_for_organization(
        test_settings, "linked_organization_id"
    )
    assert datasources == fetched_datasources


async def test_fetch_datasources_for_organization_error(
    test_settings: Settings,
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
):
    httpx_mock.add_response(
        method="GET",
        url=f"{test_settings.opt_api_base_url}/organizations/linked_organization_id/cloud_accounts?details=true",
        status_code=500,
    )

    with pytest.raises(HTTPStatusError, match="Internal Server Error"):
        await fetch_datasources_for_organization(test_settings, "linked_organization_id")


def test_redeem_entitlements_command(
    mocker: MockerFixture,
    test_settings: Settings,
):
    mock_redeem_coro = mocker.MagicMock()
    mock_redeem_entitlements = mocker.MagicMock(return_value=mock_redeem_coro)

    mocker.patch("app.commands.redeem_entitlements.redeem_entitlements", mock_redeem_entitlements)
    mock_run = mocker.patch("app.commands.redeem_entitlements.asyncio.run")
    runner = CliRunner()

    # Run the command
    result = runner.invoke(
        app,
        ["redeem-entitlements"],
    )
    assert result.exit_code == 0
    mock_run.assert_called_once_with(mock_redeem_coro)

    mock_redeem_entitlements.assert_called_once_with(
        test_settings,
    )
