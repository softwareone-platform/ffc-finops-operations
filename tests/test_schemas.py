from datetime import UTC, datetime

from app.db.models import Account, Actor, Entitlement, Organization, System
from app.enums import AccountType, ActorType, EntitlementStatus, OrganizationStatus, SystemStatus
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
        id="OPE-1234-5678",
        type=ActorType.USER,
    )
    actor_read = from_orm(ActorRead, test_actor)

    assert actor_read.id == test_actor.id
    assert actor_read.type == test_actor.type


def test_system_create_to_orm():
    data = {
        "id": "FTKN-1234-5678",
        "name": "Test System",
        "external_id": "test-system",
        "jwt_secret": "secret",
        "description": "Test Description",
        "owner": {"id": "FACC-1234-5678"},
    }

    system_create = SystemCreate(**data)
    system = to_orm(system_create, System)

    assert isinstance(system, System)
    assert system.name == data["name"]
    assert system.external_id == data["external_id"]
    assert system.jwt_secret == data["jwt_secret"]
    assert system.description == data["description"]
    assert system.type == ActorType.SYSTEM


def test_system_read_from_orm(gcp_extension: System):
    system = System(
        id="FTKN-1234-5678",
        name="Test System",
        external_id="test-system",
        jwt_secret="secret",
        description="Test Description",
        type=ActorType.SYSTEM,
        status=SystemStatus.ACTIVE,
        owner=Account(id="FACC-1234-5678", name="test", type=AccountType.AFFILIATE),
    )
    system.created_at = datetime.now(UTC)
    system.updated_at = datetime.now(UTC)
    system.created_by = gcp_extension
    system.updated_by = gcp_extension

    system_read = from_orm(SystemRead, system)

    assert system_read.id == system.id
    assert system_read.name == system.name
    assert system_read.external_id == system.external_id
    assert system_read.description == system.description
    assert system_read.created_at == system.created_at
    assert system_read.updated_at == system.updated_at
    assert system_read.created_by.id == gcp_extension.id
    assert system_read.updated_by.id == gcp_extension.id
    assert system_read.owner.id == system.owner.id


def test_entitlement_create_to_orm():
    data = {
        "name": "AWS",
        "affiliate_external_id": "ACC-123",
        "datasource_id": "container-123",
    }

    entitlement_create = EntitlementCreate(**data)
    entitlement = to_orm(entitlement_create, Entitlement)

    assert isinstance(entitlement, Entitlement)
    assert entitlement.name == data["name"]
    assert entitlement.affiliate_external_id == data["affiliate_external_id"]
    assert entitlement.datasource_id == data["datasource_id"]


def test_entitlement_read_from_orm(gcp_extension: System):
    entitlement = Entitlement(
        id="FENT-1234-5678-9012",
        name="AWS",
        affiliate_external_id="ACC-123",
        datasource_id="container-123",
        status=EntitlementStatus.ACTIVE,
    )
    # Set timestamps and audit fields after creation
    entitlement.created_at = datetime.now(UTC)
    entitlement.updated_at = datetime.now(UTC)
    entitlement.created_by = gcp_extension
    entitlement.updated_by = gcp_extension

    entitlement_read = from_orm(EntitlementRead, entitlement)

    assert entitlement_read.id == entitlement.id
    assert entitlement_read.name == entitlement.name
    assert entitlement_read.affiliate_external_id == entitlement.affiliate_external_id
    assert entitlement_read.datasource_id == entitlement.datasource_id
    assert entitlement_read.status == entitlement.status
    assert entitlement_read.created_at == entitlement.created_at
    assert entitlement_read.updated_at == entitlement.updated_at
    assert entitlement_read.created_by.id == gcp_extension.id
    assert entitlement_read.created_by.type == gcp_extension.type
    assert entitlement_read.created_by.name == gcp_extension.name
    assert entitlement_read.updated_by.id == gcp_extension.id
    assert entitlement_read.updated_by.type == gcp_extension.type
    assert entitlement_read.updated_by.name == gcp_extension.name


def test_entitlement_update_partial():
    update_data = {
        "name": "Updated AWS",
    }

    entitlement_update = EntitlementUpdate(**update_data)
    data = entitlement_update.model_dump(exclude_unset=True)

    assert len(data) == 1
    assert data["name"] == update_data["name"]


def test_organization_create_to_orm():
    data = {
        "name": "Test Org",
        "affiliate_external_id": "ORG-123",
        "user_id": "user-123",
        "currency": "USD",
    }

    org_create = OrganizationCreate(**data)
    organization = to_orm(org_create, Organization)

    assert isinstance(organization, Organization)
    assert organization.name == data["name"]
    assert organization.affiliate_external_id == data["affiliate_external_id"]
    # These fields should not be in the ORM model
    assert not hasattr(organization, "user_id")


def test_organization_read_from_orm(ffc_extension: System):
    organization = Organization(
        id="FORG-1234-5678-9012",
        name="Test Org",
        currency="EUR",
        affiliate_external_id="ORG-123",
        operations_external_id="FFC-123",
        status=OrganizationStatus.ACTIVE,
    )
    # Set timestamps and audit fields after creation
    organization.created_at = datetime.now(UTC)
    organization.updated_at = datetime.now(UTC)
    organization.created_by = ffc_extension
    organization.updated_by = ffc_extension

    org_read = from_orm(OrganizationRead, organization)

    assert org_read.id == organization.id
    assert org_read.name == organization.name
    assert org_read.currency == organization.currency
    assert org_read.affiliate_external_id == organization.affiliate_external_id
    assert org_read.operations_external_id == organization.operations_external_id
    assert org_read.status == organization.status
    assert org_read.created_at == organization.created_at
    assert org_read.updated_at == organization.updated_at
    assert org_read.created_by.id == ffc_extension.id
    assert org_read.created_by.type == ffc_extension.type
    assert org_read.created_by.name == ffc_extension.name
    assert org_read.updated_by.id == ffc_extension.id
    assert org_read.updated_by.type == ffc_extension.type
    assert org_read.updated_by.name == ffc_extension.name


def test_organization_update_partial():
    update_data = {
        "name": "Updated Org",
        "affiliate_external_id": "FFC-456",
    }

    org_update = OrganizationUpdate(**update_data)
    data = org_update.model_dump(exclude_unset=True)

    assert len(data) == 2
    assert data["name"] == update_data["name"]
    assert data["affiliate_external_id"] == update_data["affiliate_external_id"]
