from collections.abc import AsyncGenerator
from typing import Protocol, TypeVar

import fastapi_pagination
import pytest
from faker import Faker
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest_asyncio import is_async_test
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import db_engine
from app.main import app
from app.models import Entitlement, Organization
from app.repositories import EntitlementRepository, OrganizationRepository

T = TypeVar("T", bound=SQLModel)


class SQLModelFactory(Protocol[T]):
    def __call__(self, **kwargs) -> T: ...


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
    session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

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
def entitlements_repository(db_session: AsyncSession) -> EntitlementRepository:
    return EntitlementRepository(session=db_session)


@pytest.fixture
async def entitlement_factory(
    faker: Faker, entitlements_repository: EntitlementRepository
) -> SQLModelFactory[Entitlement]:
    async def _entitlement(
        sponsor_name: str | None = None,
        sponsor_external_id: str | None = None,
        sponsor_container_id: str | None = None,
    ) -> Entitlement:
        return await entitlements_repository.create(
            Entitlement(
                sponsor_name=sponsor_name or "AWS",
                sponsor_external_id=sponsor_external_id or "ACC-1234-5678",
                sponsor_container_id=sponsor_container_id or faker.uuid4(),
            )
        )

    return _entitlement


@pytest.fixture
async def entitlement_aws(entitlement_factory: SQLModelFactory[Entitlement]) -> Entitlement:
    return await entitlement_factory(sponsor_name="AWS")


@pytest.fixture
async def entitlement_gcp(entitlement_factory: SQLModelFactory[Entitlement]) -> Entitlement:
    return await entitlement_factory(sponsor_name="GCP")


@pytest.fixture
def organizations_repository(db_session: AsyncSession) -> OrganizationRepository:
    return OrganizationRepository(session=db_session)


@pytest.fixture
async def organization_factory(
    faker: Faker, organizations_repository: OrganizationRepository
) -> SQLModelFactory[Organization]:
    async def _organization(
        name: str | None = None, external_id: str | None = None
    ) -> Organization:
        return await organizations_repository.create(
            Organization(
                name=name or faker.company(),
                external_id=external_id or "ACC-1234-5678",
            )
        )

    return _organization
