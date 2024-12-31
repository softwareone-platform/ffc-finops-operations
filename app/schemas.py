import datetime
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Base
from app.enums import ActorType, EntitlementStatus


def from_orm[M: Base, S: BaseModel](cls: type[S], db_model: M) -> S:
    return cls.model_validate(db_model)


def to_orm[M: Base, S: BaseModel](schema: S, model_cls: type[M]) -> M:
    schema_data = schema.model_dump(exclude_unset=True)

    dbmodel_fields = {key: value for key, value in schema_data.items() if hasattr(model_cls, key)}

    return model_cls(**dbmodel_fields)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ActorBase(BaseSchema):
    type: ActorType


class ActorRead(ActorBase, BaseSchema):
    id: uuid.UUID


class SystemBase(BaseSchema):
    name: Annotated[str, Field(max_length=255)]
    external_id: Annotated[str, Field(max_length=255)]
    description: str | None = None


class SystemCreate(SystemBase):
    jwt_secret: Annotated[str, Field(max_length=255)]


class SystemRead(SystemBase):
    id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: ActorRead | None
    updated_by: ActorRead | None


class EntitlementBase(BaseSchema):
    sponsor_name: Annotated[str | None, Field(max_length=255)]
    sponsor_external_id: Annotated[str | None, Field(max_length=255)]
    sponsor_container_id: Annotated[str | None, Field(max_length=255)]


class EntitlementCreate(EntitlementBase):
    pass


class EntitlementUpdate(EntitlementBase):
    sponsor_name: str | None = None  # type: ignore
    sponsor_external_id: str | None = None  # type: ignore
    sponsor_container_id: str | None = None  # type: ignore


class EntitlementRead(EntitlementBase):
    id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    activated_at: datetime.datetime | None
    status: EntitlementStatus
    created_by: ActorRead | None
    updated_by: ActorRead | None


class OrganizationBase(BaseSchema):
    name: Annotated[str, Field(max_length=255)]
    external_id: Annotated[str, Field(max_length=255)]


class OrganizationCreate(OrganizationBase):
    user_id: str
    currency: str


class OrganizationRead(OrganizationBase):
    id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    organization_id: str | None
    created_by: ActorRead | None
    updated_by: ActorRead | None


class OrganizationUpdate(OrganizationBase):
    name: str | None = None  # type: ignore
    external_id: str | None = None  # type: ignore
    organization_id: str | None = None


class UserBase(BaseSchema):
    email: Annotated[str, Field(max_length=255)]
    display_name: Annotated[str, Field(max_length=255)]


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: uuid.UUID
