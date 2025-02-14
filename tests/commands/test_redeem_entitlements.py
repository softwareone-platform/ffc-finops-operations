import asyncio
from datetime import UTC, datetime

import pytest
from freezegun import freeze_time
from httpx import HTTPStatusError, ReadTimeout
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app import settings
from app.cli import app
from app.commands.redeem_entitlements import fetch_datasources_for_organization
from app.db.models import Entitlement, Organization
from app.enums import EntitlementStatus


@freeze_time("2025-03-07T10:00:00Z")
async def test_redeeem_entitlements(
    mocker: MockerFixture,
    apple_inc_organization: Organization,
    entitlement_aws: Entitlement,
    db_session: AsyncSession,
):
    mocker.patch(
        "app.commands.redeem_entitlements.fetch_datasources_for_organization",
        return_value=[
            {"id": "ds1", "type": "aws_cnr", "account_id": entitlement_aws.datasource_id},
            {"id": "ds2", "type": "azure_cnr", "account_id": "azure-account-id"},
            {"id": "ds3", "type": "gcp_cnr", "account_id": "gcp-account-id"},
            {"id": "ds4", "type": "aws_tenant", "account_id": "aws-tentant-id"},
            {"id": "ds5", "type": "azure_tenant", "account_id": "azure-tentant-id"},
            {"id": "ds", "type": "gcp_tenant", "account_id": "gcp-tentant-id"},
        ],
    )
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        ["redeem-entitlements"],
    )
    assert result.exit_code == 0

    await db_session.refresh(entitlement_aws)
    assert entitlement_aws.status == EntitlementStatus.ACTIVE
    assert entitlement_aws.redeemed_by == apple_inc_organization
    assert entitlement_aws.operations_external_id == "ds1"
    assert entitlement_aws.redeemed_at is not None
    assert entitlement_aws.redeemed_at == datetime.now(UTC)


async def test_redeeem_entitlements_error_fetching_datasources(
    mocker: MockerFixture,
    apple_inc_organization: Organization,
    entitlement_aws: Entitlement,
    db_session: AsyncSession,
):
    mocker.patch(
        "app.commands.redeem_entitlements.fetch_datasources_for_organization",
        side_effect=ReadTimeout("timed out"),
    )
    loop = asyncio.get_event_loop()
    runner = CliRunner()
    result = await loop.run_in_executor(
        None,
        runner.invoke,
        app,
        ["redeem-entitlements"],
    )
    assert result.exit_code == 0
    assert "Failed to fetch datasources: timed out" in result.stdout
    await db_session.refresh(entitlement_aws)
    assert entitlement_aws.status == EntitlementStatus.NEW
    assert entitlement_aws.redeemed_by is None


def test_fetch_datasources_for_organization(mocker: MockerFixture, httpx_mock: HTTPXMock):
    datasources = [
        {"id": "ds1", "type": "aws_cnr", "account_id": "aws-account-id"},
    ]
    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/organizations/operations_external_id/cloud_accounts?details=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        json={
            "cloud_accounts": datasources,
        },
    )

    ctx = mocker.MagicMock()
    ctx.obj = settings
    fetched_datasources = fetch_datasources_for_organization(ctx, "operations_external_id")
    assert datasources == fetched_datasources


def test_fetch_datasources_for_organization_error(mocker: MockerFixture, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/organizations/operations_external_id/cloud_accounts?details=true",
        status_code=500,
    )

    ctx = mocker.MagicMock()
    ctx.obj = settings
    with pytest.raises(HTTPStatusError, match="Internal Server Error"):
        fetch_datasources_for_organization(ctx, "operations_external_id")
