from collections.abc import AsyncGenerator, Awaitable, Callable

import fastapi_pagination
import pytest
from faker import Faker
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest_asyncio import is_async_test
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import db_engine
from app.db.handlers import EntitlementHandler, OrganizationHandler
from app.main import app
from app.models import Entitlement, Organization, UUIDModel

type ModelFactory[T: UUIDModel] = Callable[..., Awaitable[T]]


def pytest_collection_modifyitems(items):
    pytest_asyncio_tests = (item for item in items if is_async_test(item))
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.fixture(scope="session", autouse=True)
def fastapi_app() -> FastAPI:
    fastapi_pagination.add_pagination(app)
    return app


@pytest.fixture(autouse=True)
async def db_session() -> AsyncGenerator[AsyncSession]:
    session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session() as s:
        async with db_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        yield s

    async with db_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await db_engine.dispose()


@pytest.fixture
async def api_client(fastapi_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://v1/"
    ) as client:
        yield client


@pytest.fixture
def entitlements_handler(db_session: AsyncSession) -> EntitlementHandler:
    return EntitlementHandler(db_session)


@pytest.fixture
def entitlement_factory(
    faker: Faker, entitlements_handler: EntitlementHandler
) -> ModelFactory[Entitlement]:
    async def _entitlement(
        sponsor_name: str | None = None,
        sponsor_external_id: str | None = None,
        sponsor_container_id: str | None = None,
    ) -> Entitlement:
        return await entitlements_handler.create(
            Entitlement(
                sponsor_name=sponsor_name or "AWS",
                sponsor_external_id=sponsor_external_id or "ACC-1234-5678",
                sponsor_container_id=sponsor_container_id or faker.uuid4(),
            )
        )

    return _entitlement


@pytest.fixture
async def entitlement_aws(entitlement_factory: ModelFactory[Entitlement]) -> Entitlement:
    return await entitlement_factory(sponsor_name="AWS")


@pytest.fixture
async def entitlement_gcp(entitlement_factory: ModelFactory[Entitlement]) -> Entitlement:
    return await entitlement_factory(sponsor_name="GCP")


@pytest.fixture
def organizations_handler(db_session: AsyncSession) -> OrganizationHandler:
    return OrganizationHandler(db_session)


@pytest.fixture
def organization_factory(
    faker: Faker, organizations_handler: OrganizationHandler
) -> ModelFactory[Organization]:
    async def _organization(
        name: str | None = None, external_id: str | None = None
    ) -> Organization:
        return await organizations_handler.create(
            Organization(
                name=name or faker.company(),
                external_id=external_id or "ACC-1234-5678",
            )
        )

    return _organization
