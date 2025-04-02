import math
from pathlib import Path

import aiofiles
from httpx import AsyncClient

from app import settings
from app.blob_storage import upload_charges_file
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


async def test_affiliate_account_cannot_see_charges_file_in_deleted_status(
    affiliate_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    affiliate_account: Account,
):
    await charges_file_factory(
        owner=affiliate_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.DELETED,
        document_date="2025-03-25",
    )

    response = await affiliate_client.get(f"/charges?eq(owner.id,{affiliate_account.id})")
    data = response.json()
    assert response.status_code == 200
    assert data["total"] == 0


async def test_affiliate_account_can_see_charges_file_in_generated_status(
    affiliate_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    gcp_account: Account,
):
    await charges_file_factory(
        owner=gcp_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
        document_date="2025-03-25",
    )

    response = await affiliate_client.get(f"/charges?eq(owner.id,{gcp_account.id})")
    data = response.json()
    assert response.status_code == 200
    assert data["total"] == 1


async def test_affiliate_account_cannot_see_charges_file_owned_by_operations_account(
    affiliate_client: AsyncClient,
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    affiliate_account: Account,
    operations_account: Account,
):
    await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
        document_date="2025-03-25",
    )

    response = await affiliate_client.get(f"/charges?eq(owner_id,{affiliate_account.id})")
    data = response.json()
    assert response.status_code == 200
    assert data["total"] == 0


async def test_get_charges_file_by_id_with_not_existing_blob(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    charge_file = await charges_file_factory(
        owner=operations_account,
        currency="USD",
        amount=100.40,
        status=ChargesFileStatus.GENERATED,
    )

    response = await operations_client.get(f"/charges/{charge_file.id}/download")
    assert response.status_code == 404


async def test_get_charges_file_by_id(
    operations_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    operations_account: Account,
):
    charge_file = await charges_file_factory(
        owner=operations_account,
        currency="EUR",
        amount=100.40,
        document_date="2025-03-25",
        status=ChargesFileStatus.GENERATED,
    )
    base_dir = Path(__file__).resolve().parent.parent.parent
    zip_file_path = base_dir / f"azure_blob_storage/files_folder/{charge_file.id}.zip"

    async with aiofiles.open(zip_file_path, "w") as file:
        await file.write("Testing File")

    await upload_charges_file(
        file_path=str(zip_file_path),
        currency="EUR",
        year=2025,
        month=3,
    )

    response = await operations_client.get(f"/charges/{charge_file.id}/download")
    assert response.status_code == 307
    headers = response.headers["Location"]
    headers_parts = headers.split("?")[0].split("/")
    assert headers_parts[0] == "https:"
    assert headers_parts[3] == settings.azure_sa_container_name
    assert headers_parts[4] == "EUR"
    assert headers_parts[5] == "2025"
    assert headers_parts[6] == "03"
    assert headers_parts[7] == f"{charge_file.id}.zip"


async def test_get_charges_file_by_id_affiliate_account(
    affiliate_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    gcp_account: Account,
):
    charge_file = await charges_file_factory(
        owner=gcp_account,
        currency="EUR",
        amount=100.40,
        document_date="2025-03-25",
        status=ChargesFileStatus.GENERATED,
    )
    base_dir = Path(__file__).resolve().parent.parent.parent
    zip_file_path = base_dir / f"azure_blob_storage/files_folder/{charge_file.id}.zip"

    async with aiofiles.open(zip_file_path, "w") as file:
        await file.write("Testing File")

    await upload_charges_file(
        file_path=str(zip_file_path),
        currency="EUR",
        year=2025,
        month=3,
    )

    response = await affiliate_client.get(f"/charges/{charge_file.id}/download")
    assert response.status_code == 307
    headers = response.headers["Location"]
    headers_parts = headers.split("?")[0].split("/")
    assert headers_parts[0] == "https:"
    assert headers_parts[3] == settings.azure_sa_container_name
    assert headers_parts[4] == "EUR"
    assert headers_parts[5] == "2025"
    assert headers_parts[6] == "03"
    assert headers_parts[7] == f"{charge_file.id}.zip"


async def test_get_charges_file_with_status_not_generated(
    affiliate_client: AsyncClient,
    charges_file_factory: ModelFactory[ChargesFile],
    gcp_account: Account,
):
    charge_file = await charges_file_factory(
        owner=gcp_account,
        currency="EUR",
        amount=100.40,
        document_date="2025-03-25",
        status=ChargesFileStatus.DRAFT,
    )
    base_dir = Path(__file__).resolve().parent.parent.parent
    zip_file_path = base_dir / f"azure_blob_storage/files_folder/{charge_file.id}.zip"

    async with aiofiles.open(zip_file_path, "w") as file:
        await file.write("Testing File")

    await upload_charges_file(
        file_path=str(zip_file_path),
        currency="EUR",
        year=2025,
        month=3,
    )

    response = await affiliate_client.get(f"/charges/{charge_file.id}/download")
    assert response.status_code == 400


async def test_get_charges_file_by_not_existing_id(operations_client: AsyncClient):
    response = await operations_client.get("/charges/FCHG-7147-9470-8878/download")
    assert response.status_code == 404
