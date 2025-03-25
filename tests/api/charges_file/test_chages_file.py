# @pytest.mark.parametrize(
#     ("useraccount_status", "http_status"),
#     [
#         (AccountUserStatus.ACTIVE, 200),
#         (AccountUserStatus.INVITED, 200),
#         (AccountUserStatus.INVITATION_EXPIRED, 200),
#         (AccountUserStatus.DELETED, 200),
#     ],
# )
import math

from httpx import AsyncClient

from app.db.models import Account, ChargesFile
from app.enums import ChargesFileStatus
from tests.types import ModelFactory


async def test_get_charges_file_with_currency_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get("/charges?eq(currency,USD)")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_amount_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get("/charges?eq(amount,100.40)")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_gt_amount_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get("/charges?gt(amount,100)")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_gte_amount_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get("/charges?gte(amount,100.40)")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_lte_amount_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get("/charges?lte(amount,100.40)")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_lt_amount_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get("/charges?lt(amount,200.40)")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_document_data_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    charge_file = await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
        document_date="2025-03-25",
    )

    response = await operations_client.get(
        f"/charges?eq(document_date,{charge_file.document_date})"
    )  # noqa: E501
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("document_date") == "2025-03-25T00:00:00"
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200


async def test_get_charges_file_with_owner_id_data_filter(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
        document_date="2025-03-25",
    )

    response = await operations_client.get(f"/charges?eq(owner_id,{operations_account.id})")
    data = response.json()
    assert math.isclose(data["items"][0].get("amount"), 100.40)
    assert data["items"][0].get("owner").get("id") == operations_account.id
    assert response.status_code == 200
