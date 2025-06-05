from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from faker import Faker
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DatasourceExpense, Organization, System
from app.enums import DatasourceType, OrganizationStatus
from tests.types import JWTTokenFactory, ModelFactory


@pytest.fixture
async def get_organization(faker: Faker, organization_factory: ModelFactory[Organization]):
    return await organization_factory(
        operations_external_id="ORG-12345",
        name=faker.company(),
        currency="USD",
        billing_currency="EUR",
        status=OrganizationStatus.ACTIVE,
        linked_organization_id=faker.uuid4(str),
    )


async def test_get_all_expenses_empty_db(api_client: AsyncClient, ffc_jwt_token: str):
    response = await api_client.get(
        "/expenses", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


async def test_get_all_expenses_success(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    expenses = await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        "/expenses", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 200
    ret = response.json()
    assert ret["total"] > 0
    assert ret["items"][0]["organization"]["id"] == get_organization.id
    assert ret["items"][0]["year"] == expenses.year


async def test_test_get_all_expenses_success_with_and_eq_filters(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    expenses = await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        "/expenses?and(eq(month,3),eq(year,2025),eq(day,20))",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    ret = response.json()
    assert ret["total"] == 1
    assert ret["items"][0]["organization"]["id"] == get_organization.id
    assert ret["items"][0]["year"] == expenses.year
    assert ret["items"][0]["month"] == expenses.month
    assert ret["items"][0]["day"] == expenses.day


async def test_test_get_all_expenses_success_with_no_matching_filters(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        "/expenses?and(eq(month,3),eq(year,2024),eq(day,20))",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    ret = response.json()
    assert ret["total"] == 0


async def test_test_get_all_expenses_success_with_gte_filters(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=4,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 4, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        "/expenses?gte(month,3)", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 200
    ret = response.json()
    assert ret["total"] == 2


async def test_test_get_all_expenses_success_with_and_created_at_filters(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    expenses = await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        f"/expenses?eq(events.created.at,{expenses.created_at.isoformat()})",
        headers={"Authorization": f"Bearer {ffc_jwt_token}"},
    )

    assert response.status_code == 200
    ret = response.json()
    assert ret["total"] == 1
    assert ret["items"][0]["organization"]["id"] == get_organization.id
    assert ret["items"][0]["year"] == expenses.year
    assert ret["items"][0]["month"] == expenses.month
    assert ret["items"][0]["day"] == expenses.day


async def test_test_get_all_expenses_success_with_lt_filters(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    expenses = await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=4,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 4, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        "/expenses?lt(month,4)", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 200
    ret = response.json()
    assert ret["total"] == 1
    assert ret["items"][0]["organization"]["id"] == get_organization.id
    assert ret["items"][0]["year"] == expenses.year
    assert ret["items"][0]["month"] == expenses.month
    assert ret["items"][0]["day"] == expenses.day


async def test_test_get_all_expenses_success_with_wrong_filters(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    ffc_jwt_token: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=3,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 3, 20, 10, 0, 0, tzinfo=UTC),
    )
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=4,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 4, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get(
        "/expenses?gte(ciao,3)", headers={"Authorization": f"Bearer {ffc_jwt_token}"}
    )

    assert response.status_code == 400


async def test_test_get_all_expenses_with_affiliate_account_401_error(
    datasource_expense_factory: ModelFactory[DatasourceExpense],
    api_client: AsyncClient,
    aws_account: str,
    faker: Faker,
    db_session: AsyncSession,
    get_organization,
):
    await datasource_expense_factory(
        organization=get_organization,
        linked_datasource_id=faker.uuid4(str),
        linked_datasource_type=DatasourceType.AWS_CNR,
        datasource_name="First cloud account",
        datasource_id="11111111",
        year=2025,
        month=4,
        day=20,
        expenses=Decimal("123.45"),
        created_at=datetime(2025, 4, 20, 10, 0, 0, tzinfo=UTC),
    )
    response = await api_client.get("/expenses", headers={"Authorization": f"Bearer {aws_account}"})

    assert response.status_code == 401


async def test_get_all_expenses_with_expired_token(
    api_client: AsyncClient,
    jwt_token_factory: JWTTokenFactory,
    gcp_extension: System,
):
    expired_time = datetime.now(UTC) - timedelta(hours=1)
    expired_token = jwt_token_factory(
        str(gcp_extension.id),
        gcp_extension.jwt_secret,
        exp=expired_time,
    )

    response = await api_client.get(
        "/expenses", headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized."
