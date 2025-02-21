from __future__ import annotations

import datetime
import secrets
import types
import uuid
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

from app.db.models import Base
from app.enums import (
    AccountStatus,
    AccountType,
    AccountUserStatus,
    ActorType,
    DatasourceType,
    EntitlementStatus,
    OrganizationStatus,
    SystemStatus,
    UserStatus,
)


def from_orm[M: Base, S: BaseModel](schema_cls: type[S], db_model: M) -> S:
    if not issubclass(schema_cls, CommonEventsSchema):
        return schema_cls.model_validate(db_model)

    # NOTE: This is a hack, ideally this behaviour should be handled by the models,
    #       but to do it properly we need to spend more time in learning how pydantic
    #       works and possibly do quite a lot of refactoring of our schemas

    # TODO: I'm not sure Annotation is the best thing to use here, we can possibly simplify
    #       the code a lot more by using a higher level API

    events_schema_cls = schema_cls.model_fields["events"].annotation

    # TODO: Replace with schema_cls.model_fields["events"].apply_typevars_map
    #       (if that's what that metohd is for)
    if isinstance(events_schema_cls, TypeVar):
        events_schema_cls = events_schema_cls.__bound__

    if not issubclass(events_schema_cls, AuditEventsSchema):
        raise TypeError(f"Unsupported schema type: {events_schema_cls}")

    schema_values: dict[str, AuditFieldSchema | None] = {}

    for field_name, field_info in events_schema_cls.model_fields.items():
        event_field_schema_cls = field_info.annotation

        if isinstance(event_field_schema_cls, types.UnionType):
            match event_field_schema_cls.__args__:
                case (field_schema_cls, types.NoneType) | (types.NoneType, field_schema_cls):
                    event_field_schema_cls = field_schema_cls
                case _:
                    raise TypeError(f"Unsupported union type: {event_field_schema_cls.__args__}")

        if isinstance(event_field_schema_cls, TypeVar):
            event_field_schema_cls = event_field_schema_cls.__bound__

        if not issubclass(event_field_schema_cls, AuditFieldSchema):
            raise TypeError(f"Unsupported schema type: {event_field_schema_cls}")

        at_value = getattr(db_model, f"{field_name}_at")

        if at_value is None:
            schema_values[field_name] = None
            continue

        # TODO: The following will fail unless we've joined the related table

        by_value = getattr(db_model, f"{field_name}_by")

        schema_values[field_name] = event_field_schema_cls(at=at_value, by=by_value)

    events = events_schema_cls(**schema_values)

    fields = {
        field_name: getattr(db_model, field_name)
        for field_name, field_info in schema_cls.model_fields.items()
        if hasattr(db_model, field_name)
    }
    return schema_cls(**fields, events=events)


def to_orm[M: Base, S: BaseModel](schema: S, model_cls: type[M]) -> M:
    """
    Converts a Pydantic schema instance to an ORM model instance.

    This function ensures that only fields present in the ORM model are
    passed to it,preventing errors caused by extra fields.
    """
    # extract data from the schema. This will return a dict
    schema_data = schema.model_dump(exclude_unset=True)
    # filter out all the fields that are not in the ORM model
    dbmodel_fields = {key: value for key, value in schema_data.items() if hasattr(model_cls, key)}
    # create an instance of the ORM model
    return model_cls(**dbmodel_fields)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class IdSchema(BaseSchema):
    id: str


class PasswordInputSchema(BaseSchema):
    password: Annotated[SecretStr | None, Field(examples=["PKH7aqr_gwh5fgm!xdk"], default=None)]

    @field_validator("password")
    @classmethod
    def validate_password(cls, secret_value: SecretStr) -> SecretStr:
        errors = []

        value = secret_value.get_secret_value()

        if len(value) < 8:
            errors.append("Must be at least 8 characters long")
        if not any(char.isupper() for char in value):
            errors.append("Must contain at least one uppercase letter (A-Z)")
        if not any(char.islower() for char in value):
            errors.append("Must contain at least one lowercase letter (a-z)")
        if not any(char.isdigit() for char in value):
            errors.append("Must contain at least one number (0-9)")
        if not any(not char.isalnum() for char in value):  # Checks for special characters
            errors.append("Must contain at least one special character (e.g., !@#$%^&*)")

        if errors:
            raise ValueError(f"{", ".join(errors)}.")

        return secret_value


class ActorBase(BaseSchema):
    type: ActorType


class AuditFieldReference(IdSchema):
    pass


AuditFieldReferenceT = TypeVar("AuditFieldReferenceT", bound=AuditFieldReference)


class ActorRead(IdSchema, ActorBase):
    pass


class AuditFieldSchema(BaseSchema, Generic[AuditFieldReferenceT]):
    at: datetime.datetime
    by: AuditFieldReferenceT | None


class ActorReference(AuditFieldReference):
    type: ActorType
    name: Annotated[str, Field(examples=["Barack Obama"])]


class AuditEventsSchema(BaseSchema):
    created: AuditFieldSchema[ActorReference]
    updated: AuditFieldSchema[ActorReference]
    deleted: AuditFieldSchema[ActorReference] | None = None


AuditEventsT = TypeVar("AuditEventsT", bound=AuditEventsSchema)


class CommonEventsSchema(BaseSchema, Generic[AuditEventsT]):
    events: AuditEventsT


class AccountEntitlementsStats(BaseSchema):
    new: Annotated[int, Field(examples=["5"], default=0)]
    redeemed: Annotated[int, Field(examples=["4"], default=0)]
    terminated: Annotated[int, Field(examples=["12"], default=0)]


class AccountBase(BaseSchema):
    name: Annotated[
        str, Field(max_length=255, examples=["Microsoft"], description="The name of the account")
    ]
    external_id: Annotated[
        str,
        Field(
            max_length=255,
            examples=["ACC-9044-8753"],
            description="An external identifier for the account",
        ),
    ]


class AccountCreate(AccountBase):
    type: AccountType


class AccountUpdate(BaseSchema):
    name: Annotated[str | None, Field(max_length=255, examples=["Microsoft"])] = None
    external_id: Annotated[str | None, Field(max_length=255, examples=["ACC-9044-8753"])] = None


class AccountRead(IdSchema, CommonEventsSchema, AccountBase):
    entitlements_stats: AccountEntitlementsStats | None = None
    status: AccountStatus
    type: AccountType


class AccountReference(IdSchema):
    name: Annotated[str, Field(max_length=255, examples=["Microsoft"])]
    type: AccountType


class SystemBase(BaseSchema):
    name: Annotated[
        str, Field(max_length=255, examples=["FinOps For Cloud Marketplace Fulfillment Extension"])
    ]
    external_id: Annotated[str, Field(max_length=255)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    owner: AccountReference


class SystemRead(IdSchema, CommonEventsSchema, SystemBase):
    status: SystemStatus


class SystemCreate(SystemBase):
    owner: IdSchema | None = None  # type: ignore[assignment]
    jwt_secret: Annotated[
        str | None,
        Field(
            min_length=64,
            default_factory=lambda: secrets.token_hex(64),
            examples=[
                "eowlqbNqQiKVudOJ-x-nHE1MNQphe3llEzqCOR5FgnPgJj4gLIqD6utRB9qI-Lw64tR1_f3QEhoyJiyz1rsXAg"
            ],
        ),
    ] = None


class SystemUpdate(BaseSchema):
    name: str
    external_id: Annotated[str, Field(max_length=255)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    jwt_secret: Annotated[str | None, Field(min_length=64)] = None


class SystemCreateResponse(SystemRead):
    jwt_secret: str


class UserBase(BaseSchema):
    name: Annotated[str, Field(max_length=255, examples=["Lady Gaga"])]


class UserCreate(UserBase):
    email: Annotated[EmailStr, Field(max_length=255, examples=["lady.gaga@bennett.tony"])]


class UserInvitationRead(IdSchema, CommonEventsSchema, UserCreate):
    account_user: AccountUserRead | None = None
    status: UserStatus


class UserRead(IdSchema, CommonEventsSchema, UserCreate):
    status: UserStatus
    # TODO: Are these events too?
    last_login_at: datetime.datetime | None
    last_used_account: AccountReference | None


class UserReference(IdSchema, UserCreate):
    pass


class UserAcceptInvitation(PasswordInputSchema):
    invitation_token: str


class UserResetPassword(PasswordInputSchema):
    pwd_reset_token: uuid.UUID
    user_id: str | None = None


class UserUpdate(BaseSchema):
    name: str | None = None


class AccountUserBase(BaseSchema):
    status: AccountUserStatus


class AccountUserCreate(BaseSchema):
    account: IdSchema | None = None
    user: UserCreate


class AccountUserRead(IdSchema, CommonEventsSchema, AccountUserBase):
    account: AccountReference
    invitation_token: str
    invitation_token_expires_at: datetime.datetime
    joined_at: datetime.datetime | None = None


class Login(BaseSchema):
    email: Annotated[EmailStr, Field(examples=["lady.gaga@bennett.tony"])]
    password: Annotated[SecretStr, Field(examples=["PKH7aqr_gwh5fgm!xdk"])]
    account: IdSchema | None = None


class LoginRead(BaseSchema):
    user: UserReference
    account: AccountReference
    access_token: Annotated[str, Field(examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey..."])]
    refresh_token: Annotated[str, Field(examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey..."])]


class RefreshAccessToken(BaseSchema):
    account: IdSchema
    refresh_token: Annotated[str, Field(examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey..."])]


class OrganizationExpensesInfo(BaseSchema):
    limit: Annotated[Decimal, Field(max_length=255, examples=["10,000.00"], default=Decimal(0))]
    expenses_last_month: Annotated[
        Decimal, Field(max_length=255, examples=["4,321.26"], default=Decimal(0))
    ]
    expenses_this_month: Annotated[
        Decimal, Field(max_length=255, examples=["2,111.49"], default=Decimal(0))
    ]
    expenses_this_month_forecast: Annotated[
        Decimal, Field(max_length=255, examples=["5,001.12"], default=Decimal(0))
    ]
    possible_monthly_saving: Annotated[
        Decimal, Field(max_length=255, examples=["4.66"], default=Decimal(0))
    ]


class OrganizationBase(BaseSchema):
    name: Annotated[str, Field(max_length=255, examples=["Nimbus Nexus Inc."])]
    currency: Annotated[str, Field(examples=["EUR"])]
    operations_external_id: Annotated[str, Field(max_length=255, examples=["AGR-9876-5534-9172"])]


class OrganizationCreate(OrganizationBase):
    user_id: str


class OrganizationRead(IdSchema, CommonEventsSchema, OrganizationBase):
    linked_organization_id: Annotated[
        str | None, Field(max_length=255, examples=["ee7ebfaf-a222-4209-aecc-67861694a488"])
    ] = None
    status: OrganizationStatus
    expenses_info: OrganizationExpensesInfo | None = None


class OrganizationUpdate(BaseSchema):
    name: str | None = None
    operations_external_id: str | None = None


class OrganizationReference(IdSchema, OrganizationBase):
    pass


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


class EmployeeBase(BaseSchema):
    email: Annotated[str, Field(max_length=255, examples=["harry.potter@gryffindor.edu"])]
    display_name: Annotated[str, Field(max_length=255, examples=["Harry James Potter"])]
    # TODO: Common audit events too?
    created_at: datetime.datetime | None = None
    last_login: datetime.datetime | None = None
    roles_count: int | None = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeRead(EmployeeBase):
    id: uuid.UUID


class DatasourceRead(BaseSchema):
    id: uuid.UUID
    organization_id: str
    type: DatasourceType
    resources_changed_this_month: int
    expenses_so_far_this_month: float
    expenses_forecast_this_month: float
