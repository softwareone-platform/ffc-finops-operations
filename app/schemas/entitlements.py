import uuid
from typing import Annotated

from pydantic import Field

from app.enums import DatasourceType, EntitlementStatus
from app.schemas.accounts import AccountReference
from app.schemas.core import (
    ActorReference,
    AuditEventsSchema,
    AuditFieldSchema,
    BaseSchema,
    CommonEventsSchema,
    IdSchema,
)
from app.schemas.organizations import OrganizationReference


class EntitlementBase(BaseSchema):
    name: Annotated[str | None, Field(max_length=255, examples=["Microsoft CSP"])]
    affiliate_external_id: Annotated[str, Field(max_length=255, examples=["SUB-9876-5534-9172"])]
    datasource_id: Annotated[
        str | None, Field(max_length=255, examples=["1098a2fa-07c0-4f40-96c7-3bf32a213e0e"])
    ]


class EntitlementCreate(EntitlementBase):
    owner: IdSchema | None = None


class EntitlementUpdate(BaseSchema):
    name: str | None = None
    affiliate_external_id: str | None = None
    datasource_id: str | None = None


class EntitlementsEventsSchema(AuditEventsSchema):
    redeemed: AuditFieldSchema[OrganizationReference] | None = None
    terminated: AuditFieldSchema[ActorReference] | None = None


class EntitlementRead(IdSchema, CommonEventsSchema[EntitlementsEventsSchema], EntitlementBase):
    linked_datasource_id: Annotated[
        str | None, Field(max_length=255, examples=["ee7ebfaf-a222-4209-aecc-67861694a488"])
    ] = None
    linked_datasource_name: Annotated[
        str | None, Field(max_length=255, examples=["Azure Dev Subscription"])
    ] = None
    linked_datasource_type: DatasourceType | None = None
    owner: AccountReference
    status: EntitlementStatus


class EntitlementRedeem(BaseSchema):
    organization_id: uuid.UUID
