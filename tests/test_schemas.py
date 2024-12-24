import uuid
from datetime import UTC, datetime

from app.db.models import Actor, Entitlement, Organization, System
from app.enums import ActorType, EntitlementStatus
from app.schemas import (
    ActorRead,
    EntitlementCreate,
    EntitlementRead,
    EntitlementUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    SystemCreate,
    SystemRead,
    from_orm,
    to_orm,
)


def test_actor_read_from_orm():
    test_actor = Actor(
        id=uuid.uuid4(),
        type=ActorType.USER,
    )
    actor_read = from_orm(ActorRead, test_actor)

    assert actor_read.id == test_actor.id
    assert actor_read.type == test_actor.type


def test_system_create_to_orm():
    data = {
        "name": "Test System",
        "external_id": "test-system",
        "jwt_secret": "secret",
        "description": "Test Description",
    }

    system_create = SystemCreate(**data)
    system = to_orm(system_create, System)

    assert isinstance(system, System)
    assert system.name == data["name"]
    assert system.external_id == data["external_id"]
    assert system.jwt_secret == data["jwt_secret"]
    assert system.description == data["description"]
    assert system.type == ActorType.SYSTEM


def test_system_read_from_orm(test_actor: Actor):
    system = System(
        id=uuid.uuid4(),
        name="Test System",
        external_id="test-system",
        jwt_secret="secret",
        description="Test Description",
        type=ActorType.SYSTEM,
    )
    system.created_at = datetime.now(UTC)
    system.updated_at = datetime.now(UTC)
    system.created_by = test_actor
    system.updated_by = test_actor

    system_read = from_orm(SystemRead, system)

    assert system_read.id == system.id
    assert system_read.name == system.name
    assert system_read.external_id == system.external_id
    assert system_read.description == system.description
    assert system_read.created_at == system.created_at
    assert system_read.updated_at == system.updated_at
    assert system_read.created_by.id == test_actor.id
    assert system_read.updated_by.id == test_actor.id


def test_entitlement_create_to_orm():
    data = {
        "sponsor_name": "AWS",
        "sponsor_external_id": "ACC-123",
        "sponsor_container_id": "container-123",
    }

    entitlement_create = EntitlementCreate(**data)
    entitlement = to_orm(entitlement_create, Entitlement)

    assert isinstance(entitlement, Entitlement)
    assert entitlement.sponsor_name == data["sponsor_name"]
    assert entitlement.sponsor_external_id == data["sponsor_external_id"]
    assert entitlement.sponsor_container_id == data["sponsor_container_id"]


def test_entitlement_read_from_orm(test_actor: Actor):
    entitlement = Entitlement(
        id=uuid.uuid4(),
        sponsor_name="AWS",
        sponsor_external_id="ACC-123",
        sponsor_container_id="container-123",
        status=EntitlementStatus.ACTIVE,
    )
    # Set timestamps and audit fields after creation
    entitlement.created_at = datetime.now(UTC)
    entitlement.updated_at = datetime.now(UTC)
    entitlement.activated_at = datetime.now(UTC)
    entitlement.created_by = test_actor
    entitlement.updated_by = test_actor

    entitlement_read = from_orm(EntitlementRead, entitlement)

    assert entitlement_read.id == entitlement.id
    assert entitlement_read.sponsor_name == entitlement.sponsor_name
    assert entitlement_read.sponsor_external_id == entitlement.sponsor_external_id
    assert entitlement_read.sponsor_container_id == entitlement.sponsor_container_id
    assert entitlement_read.status == entitlement.status
    assert entitlement_read.activated_at == entitlement.activated_at
    assert entitlement_read.created_at == entitlement.created_at
    assert entitlement_read.updated_at == entitlement.updated_at
    assert entitlement_read.created_by.id == test_actor.id
    assert entitlement_read.updated_by.id == test_actor.id


def test_entitlement_update_partial():
    update_data = {
        "sponsor_name": "Updated AWS",
    }

    entitlement_update = EntitlementUpdate(**update_data)
    data = entitlement_update.model_dump(exclude_unset=True)

    assert len(data) == 1
    assert data["sponsor_name"] == update_data["sponsor_name"]


def test_organization_create_to_orm():
    data = {
        "name": "Test Org",
        "external_id": "ORG-123",
        "user_id": "user-123",
        "currency": "USD",
    }

    org_create = OrganizationCreate(**data)
    organization = to_orm(org_create, Organization)

    assert isinstance(organization, Organization)
    assert organization.name == data["name"]
    assert organization.external_id == data["external_id"]
    # These fields should not be in the ORM model
    assert not hasattr(organization, "user_id")
    assert not hasattr(organization, "currency")


def test_organization_read_from_orm(test_actor: Actor):
    organization = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        external_id="ORG-123",
        organization_id="FFC-123",
    )
    # Set timestamps and audit fields after creation
    organization.created_at = datetime.now(UTC)
    organization.updated_at = datetime.now(UTC)
    organization.created_by = test_actor
    organization.updated_by = test_actor

    org_read = from_orm(OrganizationRead, organization)

    assert org_read.id == organization.id
    assert org_read.name == organization.name
    assert org_read.external_id == organization.external_id
    assert org_read.organization_id == organization.organization_id
    assert org_read.created_at == organization.created_at
    assert org_read.updated_at == organization.updated_at
    assert org_read.created_by.id == test_actor.id
    assert org_read.updated_by.id == test_actor.id


def test_organization_update_partial():
    update_data = {
        "name": "Updated Org",
        "organization_id": "FFC-456",
    }

    org_update = OrganizationUpdate(**update_data)
    data = org_update.model_dump(exclude_unset=True)

    assert len(data) == 2
    assert data["name"] == update_data["name"]
    assert data["organization_id"] == update_data["organization_id"]
