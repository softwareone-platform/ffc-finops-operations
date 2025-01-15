import pytest
from httpx import AsyncClient
from pytest_mock import MockerFixture

from app.db.models import Organization, System
from app.enums import CloudAccountType
from tests.conftest import ModelFactory


# TODO: Don't fucking hardcode stuff like this, do it properly!
@pytest.fixture
def mock_api_modifier_client(mocker: MockerFixture):
    token = "MDAwZWxvY2F0aW9uIAowMDM0aWRlbnRpZmllciA2ZTFjMWNlNS1mYTZkLTQ2NjgtOTk1YS1mMzYyZWJlZjUyODAKMDAyM2NpZCBjcmVhdGVkOjE3MzY0MjY2NTIuNDQ5NzM2NgowMDE3Y2lkIHJlZ2lzdGVyOkZhbHNlCjAwMWFjaWQgcHJvdmlkZXI6b3B0c2NhbGUKMDAyZnNpZ25hdHVyZSCPs-mSJUYtnxaAagFpQNEJErJwy9tXTgQrbc-LoSDKego"  # noqa
    mocker.patch("app.api_clients.api_modifier.get_api_modifier_jwt_token", return_value=token)
    mocker.patch(
        "app.api_clients.api_modifier.APIModifierClient.get_base_url",
        return_value="https://cloudspend.velasuci.com",
    )


# TODO: Don't fucking hardcode stuff like this, do it properly!
@pytest.fixture
def optscale_organization_id():
    return "9044af7f-2f62-40cd-976f-1cbbbf1a0411"


@pytest.mark.vcr()
async def test_get_cloud_accounts_for_organization_success(
    mock_api_modifier_client,
    optscale_organization_id: str,
    organization_factory: ModelFactory[Organization],
    authenticated_client: AsyncClient,
    ffc_jwt_token: str,
    ffc_extension: System,
):
    org = await organization_factory(
        organization_id=optscale_organization_id,
    )

    response = await authenticated_client.get(f"/organizations/{org.id}/cloud-accounts")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2

    azure_cnr = next(item for item in data if item["type"] == "azure_cnr")
    azure_tenant = next(item for item in data if item["type"] == "azure_tenant")

    assert azure_cnr["organization_id"] == str(org.id)
    assert azure_cnr["type"] == CloudAccountType.AZURE_CNR.value
    assert azure_cnr["resources_changed_this_month"] == 0
    assert azure_cnr["expenses_so_far_this_month"] == 0.0
    assert azure_cnr["expenses_forecast_this_month"] == 1285.42

    assert azure_tenant["organization_id"] == str(org.id)
    assert azure_tenant["type"] == CloudAccountType.AZURE_TENANT.value
    assert azure_tenant["resources_changed_this_month"] == 0
    assert azure_tenant["expenses_so_far_this_month"] == 0.0
    assert azure_tenant["expenses_forecast_this_month"] == 0.0
