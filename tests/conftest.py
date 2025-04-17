import secrets
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Final

import jwt
import pytest
import stamina
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest_asyncio import is_async_test
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
)

from app.conf import Settings, get_settings
from app.db.base import configure_db_engine, session_factory
from app.db.models import (
    Account,
    AccountUser,
    Actor,
    Base,
    ChargesFile,
    DatasourceExpense,
    Entitlement,
    ExchangeRates,
    Organization,
    System,
    User,
)
from app.enums import (
    AccountStatus,
    AccountType,
    AccountUserStatus,
    ChargesFileStatus,
    EntitlementStatus,
    OrganizationStatus,
    SystemStatus,
    UserStatus,
)
from app.hasher import pbkdf2_sha256
from tests.db.models import ModelForTests, ParentModelForTests  # noqa: F401
from tests.types import ModelFactory

pytest_plugins = [
    "tests.fixtures.mock_api_clients",
]


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
    settings.exchange_rate_api_base_url = "https://v6.exchangerate-api.com/v6"
    settings.exchange_rate_api_token = "my_exchange_rate_api_token"
    settings.azure_sa_protocol = "http"
    settings.azure_sa_blob_endpoint = "http://azurite:10000/devstoreaccount1"
    settings.azure_sa_account_key = (
        "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
    )
    settings.smtp_sender_email = "test@example.com"
    settings.smtp_sender_name = "Test Sender"
    settings.smtp_host = "smtp.example.com"
    settings.smtp_port = 587
    settings.smtp_user = "user"
    settings.smtp_password = "password"
    settings.cli_rich_logging = False
    return settings


@pytest.fixture(scope="session")
def db_engine(test_settings: Settings) -> AsyncEngine:
    return configure_db_engine(test_settings)


@pytest.fixture(scope="session", autouse=True)
async def setup_db_tables(db_engine: AsyncEngine) -> AsyncGenerator[None]:
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield
    finally:
        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await db_engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    # Use nested transactions to avoid committing changes to the database, speeding up
    # the tests significantly and avoiding side effects between them.
    #
    # ref: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites

    async with db_engine.connect() as conn:
        outer_transaction = await conn.begin()
        session_factory.configure(bind=conn, join_transaction_mode="create_savepoint")

        try:
            async with session_factory() as s:
                yield s
        finally:
            await outer_transaction.rollback()


@pytest.fixture(scope="session")
def fastapi_app(test_settings: Settings) -> FastAPI:
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: test_settings
    return app


@pytest.fixture(scope="session")
async def app_lifespan_manager(fastapi_app: FastAPI) -> AsyncGenerator[LifespanManager, None]:
    async with LifespanManager(fastapi_app) as lifespan_manager:
        yield lifespan_manager


@pytest.fixture
async def api_client(
    fastapi_app: FastAPI,
    app_lifespan_manager: LifespanManager,
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient]:
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
        new_entitlements_count: int = 0,
        active_entitlements_count: int = 0,
        terminated_entitlements_count: int = 0,
    ) -> Account:
        account = Account(
            type=type or AccountType.AFFILIATE,
            name=name or "AWS",
            external_id=external_id or str(faker.uuid4()),
            status=status or AccountStatus.ACTIVE,
            created_by=created_by,
            updated_by=updated_by,
            new_entitlements_count=new_entitlements_count,
            active_entitlements_count=active_entitlements_count,
            terminated_entitlements_count=terminated_entitlements_count,
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
def charges_file_factory(
    faker: Faker,
    db_session: AsyncSession,
    gcp_account: Account,
) -> ModelFactory[ChargesFile]:
    async def _charges_file(
        currency: str | None = None,
        amount: Decimal | None = None,
        owner: Account | None = None,
        status: str | None = None,
        document_date: str | None = None,
        azure_blob_name: str | None = None,
    ):
        owner = owner or gcp_account
        charges_file = ChargesFile(
            id=faker.uuid4(),
            document_date=datetime.strptime(document_date, format("%Y-%m-%d")).date()
            if document_date
            else faker.date_time().date(),
            currency=currency or "USD",
            amount=amount
            or Decimal(f"{faker.pydecimal(left_digits=14, right_digits=4, positive=True)}"),
            owner=owner,
            owner_id=owner.id or gcp_account.id,
            status=status or ChargesFileStatus.DRAFT,
            azure_blob_name=azure_blob_name,
        )
        db_session.add(charges_file)
        await db_session.commit()
        await db_session.refresh(charges_file)
        return charges_file

    return _charges_file


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
        datasource_name: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> DatasourceExpense:
        organization = organization or await organization_factory()

        datasource_expense = DatasourceExpense(
            organization=organization,
            datasource_id=datasource_id or faker.uuid4(),
            datasource_name=datasource_name or "Datasource Name",
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
def exchange_rates_factory(db_session: AsyncSession) -> ModelFactory[ExchangeRates]:
    async def _exchange_rates(
        exchange_rates: dict[str, float] | None = None,
        base_currency: str = "USD",
        last_update: datetime | None = None,
        next_update: datetime | None = None,
    ):
        if exchange_rates is None:
            exchange_rates = {
                "USD": 1.0,
                "EUR": 0.9252,
                "GBP": 0.7737,
            }

        if last_update is None:
            last_update = datetime.now(UTC)

        if next_update is None:
            next_update = last_update + timedelta(days=1)

        if last_update > next_update:
            raise ValueError("Last update time must be before next update time")

        exchange_rates_model = ExchangeRates(
            api_response={
                "result": "success",
                "time_last_update_unix": int(last_update.timestamp()),
                "time_next_update_unix": int(next_update.timestamp()),
                "base_code": base_currency,
                "conversion_rates": exchange_rates,
            },
        )

        db_session.add(exchange_rates_model)
        await db_session.commit()
        await db_session.refresh(exchange_rates_model)
        return exchange_rates_model

    return _exchange_rates


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
        new_entitlements_count=10,
        active_entitlements_count=15,
        terminated_entitlements_count=50,
    )


@pytest.fixture
async def affiliate_system(
    system_factory: ModelFactory[System], affiliate_account: Account
) -> System:
    return await system_factory(external_id="FFC", owner=affiliate_account)


@pytest.fixture
def affiliate_account_jwt_token(
    system_jwt_token_factory: Callable[[System], str], affiliate_system: System
) -> str:
    return system_jwt_token_factory(affiliate_system)


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


@pytest.fixture(autouse=True, scope="session")
def stamina_testing_mode():
    stamina.set_testing(True, attempts=2)  # no backoff, maximum 2 attempts
    try:
        yield
    finally:
        stamina.set_testing(False)


# @pytest.fixture(scope="session", autouse=True)
# def mock_default_azure_credentials():
#     test_key = (
#         "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
#     )
#     with patch("app.api_clients.azure.AZURE_SA_CREDENTIALS", test_key):
#         yield


FIXED_SEED: Final[int] = 42


@pytest.hookimpl(hookwrapper=True)
def _set_fixed_random_seed(item: pytest.Item) -> None:
    """Set the randomly_seed to a fixed value for tests with the `fixed_random_seed` marker."""

    marker = item.get_closest_marker("fixed_random_seed")
    if not marker:
        yield
        return

    orig_randomly_seed = item.config.getoption("randomly_seed")

    item.config.option.randomly_seed = FIXED_SEED
    try:
        yield
    finally:
        item.config.option.randomly_seed = orig_randomly_seed


pytest_runtest_call = _set_fixed_random_seed
pytest_runtest_setup = _set_fixed_random_seed
