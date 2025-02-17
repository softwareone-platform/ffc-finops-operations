from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

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


def from_orm[M: Base, S: BaseModel](cls: type[S], db_model: M) -> S:
    return cls.model_validate(db_model)


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


class ActorRead(ActorBase, IdSchema):
    pass


class ActorReference(IdSchema):
    type: ActorType
    name: Annotated[str, Field(examples=["Barack Obama"])]


class CommonEventsSchema(BaseSchema):
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: datetime.datetime | None = None
    created_by: ActorReference | None = None
    updated_by: ActorReference | None = None
    deleted_by: ActorReference | None = None


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
    jwt_secret: Annotated[
        str | None,
        Field(
            examples=[
                "eowlqbNqQiKVudOJ-x-nHE1MNQphe3llEzqCOR5FgnPgJj4gLIqD6utRB9qI-Lw64tR1_f3QEhoyJiyz1rsXAg"
            ]
        ),
    ] = None
    owner: AccountReference


class SystemCreate(SystemBase):
    owner: IdSchema  # type: ignore


class SystemUpdate(BaseSchema):
    name: str
    external_id: Annotated[str, Field(max_length=255)]
    description: Annotated[str | None, Field(max_length=2000)] = None


class SystemRead(IdSchema, CommonEventsSchema, SystemBase):
    status: SystemStatus


class UserBase(BaseSchema):
    name: Annotated[str, Field(max_length=255, examples=["Lady Gaga"])]


class UserCreate(UserBase):
    email: Annotated[EmailStr, Field(max_length=255, examples=["lady.gaga@bennett.tony"])]


class UserCreateRead(IdSchema, CommonEventsSchema, UserCreate):
    status: UserStatus


class UserRead(IdSchema, CommonEventsSchema, UserCreate):
    status: UserStatus
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
    user: UserReference
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
    affiliate_external_id: Annotated[str, Field(max_length=255, examples=["AGR-9876-5534-9172"])]


class OrganizationCreate(OrganizationBase):
    user_id: str


class OrganizationRead(IdSchema, CommonEventsSchema, OrganizationBase):
    operations_external_id: Annotated[
        str | None, Field(max_length=255, examples=["ee7ebfaf-a222-4209-aecc-67861694a488"])
    ] = None
    status: OrganizationStatus
    expenses_info: OrganizationExpensesInfo | None = None


class OrganizationUpdate(BaseSchema):
    name: str | None = None
    affiliate_external_id: str | None = None


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


class EntitlementRead(IdSchema, CommonEventsSchema, EntitlementBase):
    operations_external_id: Annotated[
        str | None, Field(max_length=255, examples=["ee7ebfaf-a222-4209-aecc-67861694a488"])
    ] = None
    owner: AccountReference
    status: EntitlementStatus
    redeemed_at: datetime.datetime | None = None
    redeemed_by: OrganizationReference | None = None
    terminated_at: datetime.datetime | None = None
    terminated_by: ActorReference | None = None


class EntitlementRedeem(BaseSchema):
    organization_id: uuid.UUID


class EmployeeBase(BaseSchema):
    email: Annotated[str, Field(max_length=255, examples=["harry.potter@gryffindor.edu"])]
    display_name: Annotated[str, Field(max_length=255, examples=["Harry James Potter"])]
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
