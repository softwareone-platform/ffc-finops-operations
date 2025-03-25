import secrets
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from pydantic.v1.utils import deep_update
from pytest_asyncio import is_async_test
from pytest_httpx import HTTPXMock
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.conf import Settings, get_settings
from app.db import get_db_engine
from app.db.models import (
    Account,
    AccountUser,
    Actor,
    Base,
    DatasourceExpense,
    Entitlement,
    Organization,
    System,
    User,
)
from app.enums import (
    AccountStatus,
    AccountType,
    AccountUserStatus,
    EntitlementStatus,
    OrganizationStatus,
    SystemStatus,
    UserStatus,
)
from app.hasher import pbkdf2_sha256
from tests.db.models import ModelForTests, ParentModelForTests  # noqa: F401
from tests.types import ModelFactory


def pytest_collection_modifyitems(items):
    pytest_asyncio_tests = (item for item in items if is_async_test(item))
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    settings = Settings(
        _env_file=("../.env", "../.env.test"),
        _env_file_encoding="utf-8",
    )
    settings.optscale_cluster_secret = "test_cluster_secret"
    settings.optscale_rest_api_base_url = "https://opt-api.ffc.com"
    settings.optscale_auth_api_base_url = "https://opt-auth.ffc.com"
    settings.api_modifier_base_url = "https://api-modifier.ffc.com"
    settings.api_modifier_jwt_secret = "test_jwt_secret"
    settings.auth_access_jwt_secret = "auth_access_jwt_secret"
    settings.auth_refresh_jwt_secret = "auth_refresh_jwt_secret"
    return settings


@pytest.fixture(scope="session")
def db_engine(test_settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(test_settings.postgres_async_url),
        echo=test_settings.debug,
        future=True,
    )


@pytest.fixture(scope="session")
def fastapi_app(test_settings: Settings, db_engine: AsyncEngine) -> FastAPI:
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_engine] = lambda: db_engine
    return app


@pytest.fixture(scope="session", autouse=True)
async def app_lifespan_manager(fastapi_app: FastAPI) -> AsyncGenerator[LifespanManager, None]:
    async with LifespanManager(fastapi_app) as lifespan_manager:
        yield lifespan_manager


@pytest.fixture(autouse=True)
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session = async_sessionmaker(db_engine, expire_on_commit=False)

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session() as s:
            yield s
    finally:
        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await db_engine.dispose()


@pytest.fixture()
async def api_client(fastapi_app: FastAPI, app_lifespan_manager: LifespanManager):
    async with AsyncClient(
        transport=ASGITransport(app=app_lifespan_manager.app),
        base_url=f"http://localhost/{fastapi_app.root_path.removeprefix('/')}/",
    ) as client:
        yield client


@pytest.fixture
def account_factory(faker: Faker, db_session: AsyncSession) -> ModelFactory[Account]:
    async def _account(
        name: str | None = None,
        type: str | None = None,
        external_id: str | None = None,
        status: AccountStatus | None = None,
        created_by: Actor | None = None,
        updated_by: Actor | None = None,
    ) -> Account:
        account = Account(
            type=type or AccountType.AFFILIATE,
            name=name or "AWS",
            external_id=external_id or str(faker.uuid4()),
            status=status or AccountStatus.ACTIVE,
            created_by=created_by,
            updated_by=updated_by,
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)
        return account

    return _account


@pytest.fixture
def entitlement_factory(
    faker: Faker,
    db_session: AsyncSession,
    account_factory: ModelFactory[Account],
) -> ModelFactory[Entitlement]:
    async def _entitlement(
        name: str | None = None,
        affiliate_external_id: str | None = None,
        datasource_id: str | None = None,
        created_by: Actor | None = None,
        updated_by: Actor | None = None,
        owner: Account | None = None,
        status: EntitlementStatus | None = None,
    ) -> Entitlement:
        entitlement = Entitlement(
            name=name or "AWS",
            affiliate_external_id=affiliate_external_id or "ACC-1234-5678",
            datasource_id=datasource_id or faker.uuid4(),
            created_by=created_by,
            updated_by=updated_by,
            status=status or EntitlementStatus.NEW,
            owner=owner or await account_factory(),
        )
        db_session.add(entitlement)
        await db_session.commit()
        await db_session.refresh(entitlement)
        return entitlement

    return _entitlement


@pytest.fixture
def organization_factory(faker: Faker, db_session: AsyncSession) -> ModelFactory[Organization]:
    async def _organization(
        name: str | None = None,
        currency: str | None = None,
        billing_currency: str | None = None,
        operations_external_id: str | None = None,
        linked_organization_id: str | None = None,
        created_by: Actor | None = None,
        updated_by: Actor | None = None,
        status: OrganizationStatus = OrganizationStatus.ACTIVE,
    ) -> Organization:
        organization = Organization(
            name=name or faker.company(),
            currency=currency or "EUR",
            billing_currency=billing_currency or "USD",
            operations_external_id=operations_external_id or "AGR-1234-5678-9012",
            linked_organization_id=linked_organization_id,
            created_by=created_by,
            updated_by=updated_by,
            status=status,
        )
        db_session.add(organization)
        await db_session.commit()
        await db_session.refresh(organization)
        return organization

    return _organization


@pytest.fixture
def system_factory(
    faker: Faker, db_session: AsyncSession, account_factory: ModelFactory[Account]
) -> ModelFactory[System]:
    async def _system(
        name: str | None = None,
        external_id: str | None = None,
        jwt_secret: str | None = None,
        owner: Account | None = None,
        status: SystemStatus = SystemStatus.ACTIVE,
    ) -> System:
        owner = owner or await account_factory()
        system = System(
            name=name or faker.company(),
            external_id=external_id or str(uuid.uuid4()),
            jwt_secret=jwt_secret or secrets.token_hex(32),
            owner=owner or await account_factory(),
            status=status,
        )
        db_session.add(system)
        await db_session.commit()
        await db_session.refresh(system)
        return system

    return _system


@pytest.fixture
def accountuser_factory(db_session: AsyncSession):
    async def _accountuser(
        user_id: str,
        account_id: str,
        status: AccountUserStatus = AccountUserStatus.ACTIVE,
        invitation_token: str | None = None,
        invitation_token_expires_at: datetime | None = None,
    ) -> AccountUser:
        account_user = AccountUser(
            user_id=user_id,
            account_id=account_id,
            status=status,
            invitation_token=invitation_token,
            invitation_token_expires_at=invitation_token_expires_at,
        )
        db_session.add(account_user)
        await db_session.commit()
        await db_session.refresh(account_user)
        return account_user

    return _accountuser


@pytest.fixture
def user_factory(
    faker: Faker, db_session: AsyncSession, account_factory: ModelFactory[Account]
) -> ModelFactory[User]:
    async def _user(
        name: str | None = None,
        email: str | None = None,
        password: str | None = None,
        pwd_reset_token: str | None = None,
        pwd_reset_token_expires_at: datetime | None = None,
        status: UserStatus = UserStatus.ACTIVE,
        account: Account | None = None,
        accountuser_status: AccountUserStatus = AccountUserStatus.ACTIVE,
    ) -> User:
        account = account or await account_factory()
        user = User(
            name=name or faker.name(),
            email=email or faker.email(),
            password=pbkdf2_sha256.hash(password or "mySuperPass123$"),
            last_used_account=account,
            status=status,
            pwd_reset_token=pwd_reset_token,
            pwd_reset_token_expires_at=pwd_reset_token_expires_at,
        )

        db_session.add(user)
        account_user = AccountUser(
            user=user,
            account=account or await account_factory(),
            status=accountuser_status,
        )
        db_session.add(account_user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _user


@pytest.fixture
def jwt_token_factory() -> Callable[
    [str, str, str | None, datetime | None, datetime | None, datetime | None], str
]:
    def _jwt_token(
        subject: str,
        secret: str,
        account_id: str | None = None,
        exp: datetime | None = None,
        nbf: datetime | None = None,
        iat: datetime | None = None,
    ) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": subject,
            "iat": iat or now,
            "nbf": nbf or now,
            "exp": exp or now + timedelta(minutes=5),
        }
        if account_id:
            claims["account_id"] = account_id

        return jwt.encode(
            claims,
            secret,
            algorithm="HS256",
        )

    return _jwt_token


@pytest.fixture
def system_jwt_token_factory(
    jwt_token_factory: Callable[
        [str, str, str | None, datetime | None, datetime | None, datetime | None], str
    ],
) -> Callable[[System], str]:
    def _system_jwt_token(system: System) -> str:
        now = datetime.now(UTC)

        return jwt_token_factory(
            str(system.id),
            system.jwt_secret,
            None,
            now + timedelta(minutes=5),
            now,
            now,
        )

    return _system_jwt_token


@pytest.fixture
def datasource_expense_factory(
    faker: Faker,
    db_session: AsyncSession,
    organization_factory: ModelFactory[Organization],
) -> ModelFactory[DatasourceExpense]:
    async def _datasource_expense(
        organization: Organization | None = None,
        year: int = 2025,
        month: int = 3,
        month_expenses: float = 123.45,
        datasource_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> DatasourceExpense:
        organization = organization or await organization_factory()

        datasource_expense = DatasourceExpense(
            organization=organization,
            datasource_id=datasource_id or faker.uuid4(),
            year=year,
            month=month,
            month_expenses=month_expenses,
            created_at=created_at or datetime.now(UTC) - timedelta(days=7),
            updated_at=updated_at or datetime.now(UTC) - timedelta(days=7),
        )
        db_session.add(datasource_expense)
        await db_session.commit()
        await db_session.refresh(datasource_expense)
        return datasource_expense

    return _datasource_expense


@pytest.fixture
async def aws_account(account_factory: ModelFactory[Account]) -> Account:
    return await account_factory(name="AWS", type=AccountType.AFFILIATE)


@pytest.fixture
async def gcp_account(account_factory: ModelFactory[Account]) -> Account:
    return await account_factory(name="GCP", type=AccountType.AFFILIATE)


@pytest.fixture
async def gcp_extension(system_factory: ModelFactory[System], gcp_account: Account) -> System:
    return await system_factory(external_id="GCP", owner=gcp_account)


@pytest.fixture
async def aws_extension(system_factory: ModelFactory[System], aws_account: Account) -> System:
    return await system_factory(external_id="AWS", owner=aws_account)


@pytest.fixture
async def operations_account(account_factory: ModelFactory[Account]) -> Account:
    return await account_factory(name="SoftwareOne", type=AccountType.OPERATIONS)


@pytest.fixture
async def affiliate_account(
    account_factory: ModelFactory[Account], ffc_extension: System
) -> Account:
    return await account_factory(
        name="Microsoft",
        type=AccountType.AFFILIATE,
        created_by=ffc_extension,
        updated_by=ffc_extension,
    )


@pytest.fixture
def gcp_jwt_token(system_jwt_token_factory: Callable[[System], str], gcp_extension: System) -> str:
    return system_jwt_token_factory(gcp_extension)


@pytest.fixture
async def ffc_extension(
    system_factory: ModelFactory[System], operations_account: Account
) -> System:
    return await system_factory(external_id="FFC", owner=operations_account)


@pytest.fixture
def ffc_jwt_token(system_jwt_token_factory: Callable[[System], str], ffc_extension: System) -> str:
    return system_jwt_token_factory(ffc_extension)


@pytest.fixture
async def entitlement_aws(
    entitlement_factory: ModelFactory[Entitlement], aws_extension: System
) -> Entitlement:
    return await entitlement_factory(
        name="AWS",
        owner=aws_extension.owner,
        created_by=aws_extension,
        updated_by=aws_extension,
    )


@pytest.fixture
async def entitlement_gcp(
    entitlement_factory: ModelFactory[Entitlement],
    gcp_extension: System,
) -> Entitlement:
    return await entitlement_factory(
        name="GCP",
        owner=gcp_extension.owner,
        created_by=gcp_extension,
        updated_by=gcp_extension,
    )


@pytest.fixture
def affiliate_client(api_client: AsyncClient, gcp_jwt_token: str) -> AsyncClient:
    api_client.headers["Authorization"] = f"Bearer {gcp_jwt_token}"
    return api_client


@pytest.fixture
def operations_client(api_client: AsyncClient, ffc_jwt_token: str) -> AsyncClient:
    api_client.headers["Authorization"] = f"Bearer {ffc_jwt_token}"
    return api_client


@pytest.fixture
async def apple_inc_organization(organization_factory: ModelFactory[Organization]) -> Organization:
    return await organization_factory(
        name="Apple Inc.",
        currency="USD",
        linked_organization_id=str(uuid.uuid4()),
    )


class MockOptscaleClient:
    def __init__(self, test_settings: Settings, httpx_mock: HTTPXMock):
        self.test_settings = test_settings
        self.httpx_mock = httpx_mock

    def add_mock_response(self, method: str, url: str, **kwargs: Any) -> None:
        self.httpx_mock.add_response(
            method=method,
            url=f"{self.test_settings.optscale_rest_api_base_url}/{url.removeprefix('/')}",
            match_headers={"Secret": self.test_settings.optscale_cluster_secret},
            **kwargs,
        )

    def mock_fetch_datasources_for_organization(
        self,
        organization: Organization,
        cloud_account_configs: list[dict[str, Any]] | None = None,
        status_code: int = status.HTTP_200_OK,
    ):
        if organization.linked_organization_id is None:
            raise ValueError("Organization has no linked organization ID")

        def cloud_account_details_factory(config: dict[str, Any]) -> dict[str, Any]:
            return deep_update(
                {
                    "id": str(uuid.uuid4()),
                    "deleted_at": 0,
                    "created_at": 1729683941,
                    "name": "CPA (Development and Test)",
                    "type": "azure_cnr",
                    "organization_id": organization.linked_organization_id,
                    "account_id": str(uuid.uuid4()),
                    "details": {
                        "cost": 123.45,
                        "forecast": 1099.0,
                        "tracked": 2,
                        "last_month_cost": 987.65,
                    },
                },
                config,
            )

        json = None

        if cloud_account_configs is not None:
            json = {
                "cloud_accounts": [
                    cloud_account_details_factory(config) for config in cloud_account_configs
                ]
            }

        self.add_mock_response(
            "GET",
            f"organizations/{organization.linked_organization_id}/cloud_accounts?details=true",
            json=json,
            status_code=status_code,
        )


@pytest.fixture
def mock_optscale_client(test_settings: Settings, httpx_mock: HTTPXMock) -> MockOptscaleClient:
    return MockOptscaleClient(test_settings, httpx_mock)
