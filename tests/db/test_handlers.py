import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.handlers import (
    ConstraintViolationError,
    DatabaseError,
    EntitlementHandler,
    NotFoundError,
    OrganizationHandler,
    SystemHandler,
)
from app.db.models import Actor, Entitlement, Organization, System
from app.enums import ActorType, EntitlementStatus

# =========================================================
# Entitlement Handler Tests
# =========================================================


async def test_create_entitlement(
    db_session: AsyncSession,
    test_actor: Actor,
):
    entitlement = Entitlement(
        sponsor_name="AWS",
        sponsor_external_id="ACC-123",
        sponsor_container_id="container-123",
        created_by=test_actor,
        updated_by=test_actor,
    )

    entitlements_handler = EntitlementHandler(db_session)

    created = await entitlements_handler.create(entitlement)

    # Verify in DB directly
    result = await db_session.execute(select(Entitlement).where(Entitlement.id == created.id))
    db_entitlement = result.scalar_one()

    assert db_entitlement.sponsor_name == "AWS"
    assert db_entitlement.status == EntitlementStatus.NEW
    assert db_entitlement.created_at is not None
    assert db_entitlement.updated_at is not None
    assert db_entitlement.created_by_id == test_actor.id
    assert db_entitlement.updated_by_id == test_actor.id


async def test_get_entitlement(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create directly in DB
    entitlement = Entitlement(
        sponsor_name="AWS",
        sponsor_external_id="ACC-123",
        sponsor_container_id="container-123",
        created_by=test_actor,
        updated_by=test_actor,
    )
    db_session.add(entitlement)
    await db_session.commit()
    await db_session.refresh(entitlement)

    # Get using handler
    entitlements_handler = EntitlementHandler(db_session)
    fetched = await entitlements_handler.get(entitlement.id)

    assert fetched.id == entitlement.id
    assert fetched.sponsor_name == "AWS"
    assert fetched.created_by_id == test_actor.id
    assert fetched.updated_by_id == test_actor.id


async def test_get_entitlement_not_found(db_session: AsyncSession):
    entitlements_handler = EntitlementHandler(db_session)

    with pytest.raises(NotFoundError):
        await entitlements_handler.get(uuid.uuid4())


async def test_update_entitlement(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create directly in DB
    entitlement = Entitlement(
        sponsor_name="AWS",
        sponsor_external_id="ACC-123",
        sponsor_container_id="container-123",
        created_by=test_actor,
        updated_by=test_actor,
    )
    db_session.add(entitlement)
    await db_session.commit()
    await db_session.refresh(entitlement)

    entitlements_handler = EntitlementHandler(db_session)
    updated = await entitlements_handler.update(
        entitlement.id,
        {
            "sponsor_name": "Updated AWS",
            "status": EntitlementStatus.ACTIVE.value,
            "activated_at": datetime.now(UTC),
            "updated_by_id": test_actor.id,
        },
    )

    # Verify in DB directly
    result = await db_session.execute(select(Entitlement).where(Entitlement.id == updated.id))
    db_entitlement = result.scalar_one()

    assert db_entitlement.sponsor_name == "Updated AWS"
    assert db_entitlement.status == EntitlementStatus.ACTIVE.value
    assert db_entitlement.activated_at is not None
    assert db_entitlement.created_by_id == test_actor.id
    assert db_entitlement.updated_by_id == test_actor.id


async def test_update_entitlement_not_found(db_session: AsyncSession):
    entitlements_handler = EntitlementHandler(db_session)

    with pytest.raises(NotFoundError):
        await entitlements_handler.update(uuid.uuid4(), {"sponsor_name": "Updated AWS"})


async def test_fetch_page_entitlements(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create 5 entitlements directly in DB
    for i in range(5):
        entitlement = Entitlement(
            sponsor_name=f"AWS-{i}",
            sponsor_external_id=f"ACC-{i}",
            sponsor_container_id=f"container-{i}",
            created_by=test_actor,
            updated_by=test_actor,
        )
        db_session.add(entitlement)
    await db_session.commit()
    await db_session.refresh(entitlement)

    # Test first page
    entitlements_handler = EntitlementHandler(db_session)
    items = await entitlements_handler.fetch_page(limit=3, offset=0)
    assert len(items) == 3
    for item in items:
        assert item.created_by_id == test_actor.id
        assert item.updated_by_id == test_actor.id

    # Test second page
    items = await entitlements_handler.fetch_page(limit=3, offset=3)
    assert len(items) == 2


async def test_count_entitlements(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create 5 entitlements directly in DB
    for i in range(5):
        entitlement = Entitlement(
            sponsor_name=f"AWS-{i}",
            sponsor_external_id=f"ACC-{i}",
            sponsor_container_id=f"container-{i}",
            created_by=test_actor,
            updated_by=test_actor,
        )
        db_session.add(entitlement)
    await db_session.commit()
    await db_session.refresh(entitlement)

    entitlements_handler = EntitlementHandler(db_session)
    count = await entitlements_handler.count()
    assert count == 5


# =========================================================
# Organization Handler Tests
# =========================================================


async def test_create_organization(
    db_session: AsyncSession,
    test_actor: Actor,
):
    org = Organization(
        name="Test Org",
        external_id="ORG-123",
        created_by=test_actor,
        updated_by=test_actor,
    )

    organizations_handler = OrganizationHandler(db_session)
    created = await organizations_handler.create(org)

    # Verify in DB directly
    result = await db_session.execute(select(Organization).where(Organization.id == created.id))
    db_org = result.scalar_one()

    assert db_org.name == "Test Org"
    assert db_org.external_id == "ORG-123"
    assert db_org.created_by_id == test_actor.id
    assert db_org.updated_by_id == test_actor.id


async def test_create_organization_duplicate_external_id(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create first organization directly in DB
    org1 = Organization(
        name="Test Org 1",
        external_id="ORG-123",
        created_by=test_actor,
        updated_by=test_actor,
    )
    db_session.add(org1)
    await db_session.commit()
    await db_session.refresh(org1)

    # Try to create another with same external_id using handler
    org2 = Organization(
        name="Test Org 2",
        external_id="ORG-123",
        created_by=test_actor,
        updated_by=test_actor,
    )
    organizations_handler = OrganizationHandler(db_session)
    with pytest.raises(ConstraintViolationError):
        await organizations_handler.create(org2)


async def test_fetch_page_organizations(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create 5 organizations directly in DB
    for i in range(5):
        org = Organization(
            name=f"Test Org {i}",
            external_id=f"ORG-{i}",
            created_by=test_actor,
            updated_by=test_actor,
        )
        db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    organizations_handler = OrganizationHandler(db_session)

    # Test first page
    items = await organizations_handler.fetch_page(limit=2, offset=0)
    assert len(items) == 2
    for item in items:
        assert item.created_by_id == test_actor.id
        assert item.updated_by_id == test_actor.id

    # Test second page
    items = await organizations_handler.fetch_page(limit=2, offset=2)
    assert len(items) == 2

    # Test last page
    items = await organizations_handler.fetch_page(limit=2, offset=4)
    assert len(items) == 1


async def test_count_organizations(
    db_session: AsyncSession,
    test_actor: Actor,
):
    # Create 3 organizations directly in DB
    for i in range(3):
        org = Organization(
            name=f"Test Org {i}",
            external_id=f"ORG-{i}",
            created_by=test_actor,
            updated_by=test_actor,
        )
        db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    organizations_handler = OrganizationHandler(db_session)
    count = await organizations_handler.count()
    assert count == 3


# =========================================================
# System Handler Tests
# =========================================================


async def test_create_system(
    db_session: AsyncSession,
):
    system = System(
        name="Test System",
        external_id="test-system",
        jwt_secret="secret",
    )

    system_handler = SystemHandler(db_session)
    created = await system_handler.create(system)

    # Verify in DB directly
    result = await db_session.execute(select(System).where(System.id == created.id))
    db_system = result.scalar_one()

    assert db_system.name == "Test System"
    assert db_system.external_id == "test-system"
    assert db_system.jwt_secret == "secret"
    assert db_system.type == ActorType.SYSTEM


async def test_get_system(
    db_session: AsyncSession,
):
    # Create directly in DB
    system = System(
        name="Test System",
        external_id="test-system",
        jwt_secret="secret",
    )
    db_session.add(system)
    await db_session.commit()
    await db_session.refresh(system)

    system_handler = SystemHandler(db_session)
    # Get using handler
    fetched = await system_handler.get(system.id)

    assert fetched.id == system.id
    assert fetched.name == "Test System"
    assert fetched.type == ActorType.SYSTEM


async def test_create_system_duplicate_external_id(
    db_session: AsyncSession,
):
    # Create first system directly in DB
    system1 = System(
        name="Test System 1",
        external_id="test-system",
        jwt_secret="secret1",
    )
    db_session.add(system1)
    await db_session.commit()
    await db_session.refresh(system1)

    # Try to create another with same external_id using handler
    system2 = System(
        name="Test System 2",
        external_id="test-system",
        jwt_secret="secret2",
    )
    system_handler = SystemHandler(db_session)

    with pytest.raises(ConstraintViolationError):
        await system_handler.create(system2)


async def test_system_encrypted_jwt_secret(
    db_session: AsyncSession,
):
    secret = "test-secret"
    system = System(
        name="Test System",
        external_id="test-system",
        jwt_secret=secret,
    )
    system_handler = SystemHandler(db_session)

    created = await system_handler.create(system)

    # Verify in DB directly
    result = await db_session.execute(select(System).where(System.id == created.id))
    db_system = result.scalar_one()

    assert db_system.jwt_secret == secret  # Should be automatically decrypted


async def test_fetch_page_systems(
    db_session: AsyncSession,
):
    # Create 4 systems directly in DB
    for i in range(4):
        system = System(
            name=f"Test System {i}",
            external_id=f"system-{i}",
            jwt_secret=f"secret-{i}",
        )
        db_session.add(system)
    await db_session.commit()
    await db_session.refresh(system)

    system_handler = SystemHandler(db_session)
    # Test first page
    items = await system_handler.fetch_page(limit=2, offset=0)
    assert len(items) == 2
    for item in items:
        assert item.type == ActorType.SYSTEM

    # Test second page
    items = await system_handler.fetch_page(limit=2, offset=2)
    assert len(items) == 2

    # Test empty page
    items = await system_handler.fetch_page(limit=2, offset=4)
    assert len(items) == 0


async def test_count_systems(db_session: AsyncSession):
    # Create 4 systems directly in DB
    for i in range(4):
        system = System(
            name=f"Test System {i}",
            external_id=f"system-{i}",
            jwt_secret=f"secret-{i}",
        )
        db_session.add(system)
    await db_session.commit()
    await db_session.refresh(system)

    system_handler = SystemHandler(db_session)
    count = await system_handler.count()
    assert count == 4


async def test_update_system_jwt_secret(db_session: AsyncSession):
    system = System(
        name="Test System",
        external_id="test-system",
        jwt_secret="secret",
        created_by=None,
        updated_by=None,
    )
    db_session.add(system)
    await db_session.commit()
    await db_session.refresh(system)

    system_handler = SystemHandler(db_session)
    updated = await system_handler.update(system.id, {"jwt_secret": "new-secret"})

    assert updated.jwt_secret == "new-secret"


async def test_get_system_db_error(
    db_session: AsyncSession,
):
    # Create directly in DB
    system = System(
        name="Test System",
        external_id="test-system",
        jwt_secret="secret",
    )
    db_session.add(system)
    await db_session.commit()
    await db_session.refresh(system)

    system_handler = SystemHandler(db_session)
    # Get using handl
    with pytest.raises(DatabaseError):
        await system_handler.get("abcd")
