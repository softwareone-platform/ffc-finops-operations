import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, TypeVar

import jwt
import pytest
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest_asyncio import is_async_test
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import settings
from app.db import db_engine
from app.db.models import Actor, Base, Entitlement, Organization, System

ModelT = TypeVar("ModelT", bound=Base)
ModelFactory = Callable[..., Awaitable[ModelT]]


class JWTTokenFactory(Protocol):
    def __call__(
        self,
        user_id: str,
        secret: str,
        exp: datetime | None = None,
        iat: datetime | None = None,
        nbf: datetime | None = None,
    ) -> str: ...


def pytest_collection_modifyitems(items):
    pytest_asyncio_tests = (item for item in items if is_async_test(item))
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.fixture(scope="session")
def mock_settings() -> None:
    settings.opt_cluster_secret = "test_cluster_secret"
    settings.opt_api_base_url = "https://opt-api.ffc.com"
    settings.opt_auth_base_url = "https://opt-auth.ffc.com"
    settings.api_modifier_base_url = "https://api-modifier.ffc.com"
    settings.api_modifier_jwt_secret = "test_jwt_secret"


@pytest.fixture(scope="session", autouse=True)
async def fastapi_app(mock_settings) -> AsyncGenerator[Any, None]:
    from app.main import app

    async with LifespanManager(app) as lifespan_manager:
        yield lifespan_manager.app


@pytest.fixture(autouse=True)
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    session = async_sessionmaker(db_engine, expire_on_commit=False)

    async with session() as s:
        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield s

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await db_engine.dispose()


@pytest.fixture(scope="session")
async def api_client(fastapi_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://v1/"
    ) as client:
        yield client


@pytest.fixture
def entitlement_factory(faker: Faker, db_session: AsyncSession) -> ModelFactory[Entitlement]:
    async def _entitlement(
        sponsor_name: str | None = None,
        sponsor_external_id: str | None = None,
        sponsor_container_id: str | None = None,
        created_by: Actor | None = None,
        updated_by: Actor | None = None,
    ) -> Entitlement:
        entitlement = Entitlement(
            sponsor_name=sponsor_name or "AWS",
            sponsor_external_id=sponsor_external_id or "ACC-1234-5678",
            sponsor_container_id=sponsor_container_id or faker.uuid4(),
            created_by=created_by,
            updated_by=updated_by,
        )
        db_session.add(entitlement)
        await db_session.commit()
        await db_session.refresh(entitlement)
        return entitlement

    return _entitlement


@pytest.fixture
async def entitlement_aws(
    entitlement_factory: ModelFactory[Entitlement], gcp_extension: System
) -> Entitlement:
    return await entitlement_factory(
        sponsor_name="AWS", created_by=gcp_extension, updated_by=gcp_extension
    )


@pytest.fixture
async def entitlement_gcp(entitlement_factory: ModelFactory[Entitlement]) -> Entitlement:
    return await entitlement_factory(sponsor_name="GCP")


@pytest.fixture
def organization_factory(faker: Faker, db_session: AsyncSession) -> ModelFactory[Organization]:
    async def _organization(
        name: str | None = None,
        external_id: str | None = None,
        organization_id: str | None = None,
        created_by: Actor | None = None,
        updated_by: Actor | None = None,
    ) -> Organization:
        organization = Organization(
            name=name or faker.company(),
            external_id=external_id or "ACC-1234-5678",
            organization_id=organization_id,
            created_by=created_by,
            updated_by=updated_by,
        )
        db_session.add(organization)
        await db_session.commit()
        await db_session.refresh(organization)
        return organization

    return _organization


@pytest.fixture
def system_factory(faker: Faker, db_session: AsyncSession) -> ModelFactory[System]:
    async def _system(
        name: str | None = None,
        external_id: str | None = None,
        jwt_secret: str | None = None,
    ) -> System:
        system = System(
            name=name or faker.company(),
            external_id=external_id or "GCP",
            jwt_secret=jwt_secret or secrets.token_hex(32),
        )
        db_session.add(system)
        await db_session.commit()
        await db_session.refresh(system)
        return system

    return _system


@pytest.fixture
def jwt_token_factory() -> (
    Callable[[str, str, datetime | None, datetime | None, datetime | None], str]
):
    def _jwt_token(
        subject: str,
        secret: str,
        exp: datetime | None = None,
        nbf: datetime | None = None,
        iat: datetime | None = None,
    ) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": subject,
                "iat": iat or now,
                "nbf": nbf or now,
                "exp": exp or now + timedelta(minutes=5),
            },
            secret,
            algorithm="HS256",
        )

    return _jwt_token


@pytest.fixture
def system_jwt_token_factory(
    jwt_token_factory: Callable[[str, str, datetime | None, datetime | None, datetime | None], str],
) -> Callable[[System], str]:
    def _system_jwt_token(system: System) -> str:
        now = datetime.now(UTC)

        return jwt_token_factory(
            str(system.id),
            system.jwt_secret,
            now + timedelta(minutes=5),
            now,
            now,
        )

    return _system_jwt_token


@pytest.fixture
async def gcp_extension(system_factory: ModelFactory[System]) -> System:
    return await system_factory(external_id="GCP")


@pytest.fixture
def gcp_jwt_token(system_jwt_token_factory: Callable[[System], str], gcp_extension: System) -> str:
    return system_jwt_token_factory(gcp_extension)


@pytest.fixture
async def ffc_extension(system_factory: ModelFactory[System]) -> System:
    return await system_factory(external_id="FFC")


@pytest.fixture
def ffc_jwt_token(system_jwt_token_factory: Callable[[System], str], ffc_extension: System) -> str:
    return system_jwt_token_factory(ffc_extension)


@pytest.fixture
def authenticated_client(api_client: AsyncClient, gcp_jwt_token: str) -> AsyncClient:
    api_client.headers["Authorization"] = f"Bearer {gcp_jwt_token}"
    return api_client
