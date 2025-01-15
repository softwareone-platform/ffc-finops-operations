import uuid

from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from app import settings
from app.db.models import Organization
from app.enums import CloudAccountType
from tests.conftest import ModelFactory


async def test_get_cloud_accounts_for_organization_success(
    organization_factory: ModelFactory[Organization],
    mocker: MockerFixture,
    httpx_mock: HTTPXMock,
    authenticated_client: AsyncClient,
):
    org = await organization_factory(
        organization_id=str(uuid.uuid4()),
    )

    optscale_response = {
        "cloud_accounts": [
            {
                "deleted_at": 0,
                "id": "6d55d940-ba4a-4e80-8493-57b3fdf5c331",
                "created_at": 1729683941,
                "name": "CPA (Development and Test)",
                "type": "azure_cnr",
                "config": {
                    "client_id": "cd945f4b-0554-4a16-9a09-96a2f30bc0ef",
                    "tenant": "1dc9b339-fadb-432e-86df-423c38a0fcb8",
                    "skipped_subscriptions": {
                        "CPA (Development and Test)": "Cloud account for this account already exist"
                    },
                    "subscription_id": "91819a1c-c7d3-4b89-bc9f-39f85bff4666",
                    "expense_import_scheme": "usage",
                },
                "organization_id": "9044af7f-2f62-40cd-976f-1cbbbf1a0411",
                "auto_import": True,
                "import_period": 1,
                "last_import_at": 1733151640,
                "last_import_modified_at": 0,
                "account_id": "91819a1c-c7d3-4b89-bc9f-39f85bff4666",
                "process_recommendations": True,
                "cleaned_at": 0,
                "parent_id": "48108421-7334-4a2c-ac7b-0160476dc790",
                "details": {
                    "cost": 0,
                    "forecast": 1099.0,
                    "tracked": 0,
                    "last_month_cost": 2909.1068521455545,
                    "discovery_infos": [],
                },
            },
            {
                "deleted_at": 0,
                "id": "48108421-7334-4a2c-ac7b-0160476dc790",
                "created_at": 1729683895,
                "name": "Test",
                "type": "azure_tenant",
                "config": {
                    "client_id": "cd945f4b-0554-4a16-9a09-96a2f30bc0ef",
                    "tenant": "1dc9b339-fadb-432e-86df-423c38a0fcb8",
                    "skipped_subscriptions": {
                        "CPA (Development and Test)": "Cloud account for this account already exist"
                    },
                },
                "organization_id": "9044af7f-2f62-40cd-976f-1cbbbf1a0411",
                "auto_import": False,
                "import_period": 1,
                "last_import_at": 0,
                "last_import_modified_at": 0,
                "account_id": "1dc9b339-fadb-432e-86df-423c38a0fcb8",
                "process_recommendations": True,
                "last_import_attempt_at": 0,
                "last_import_attempt_error": None,
                "last_getting_metrics_at": 0,
                "last_getting_metric_attempt_at": 0,
                "last_getting_metric_attempt_error": None,
                "cleaned_at": 0,
                "parent_id": None,
                "details": {
                    "cost": 0,
                    "forecast": 0.0,
                    "tracked": 0,
                    "last_month_cost": 0,
                    "discovery_infos": [],
                },
            },
        ]
    }

    httpx_mock.add_response(
        method="GET",
        url=f"{settings.opt_api_base_url}/organizations/{org.organization_id}/cloud_accounts?details=true",
        match_headers={"Secret": settings.opt_cluster_secret},
        json=optscale_response,
    )

    response = await authenticated_client.get(
        f"/organizations/{org.id}/cloud-accounts",
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2

    azure_cnr = next(item for item in data if item["type"] == "azure_cnr")
    azure_tenant = next(item for item in data if item["type"] == "azure_tenant")

    assert azure_cnr["organization_id"] == str(org.id)
    assert azure_cnr["type"] == CloudAccountType.AZURE_CNR.value
    assert azure_cnr["resources_changed_this_month"] == 0
    assert azure_cnr["expenses_so_far_this_month"] == 0.0
    assert azure_cnr["expenses_forecast_this_month"] == 1099.0

    assert azure_tenant["organization_id"] == str(org.id)
    assert azure_tenant["type"] == CloudAccountType.AZURE_TENANT.value
    assert azure_tenant["resources_changed_this_month"] == 0
    assert azure_tenant["expenses_so_far_this_month"] == 0.0
    assert azure_tenant["expenses_forecast_this_month"] == 0.0
