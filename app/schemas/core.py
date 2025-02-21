from __future__ import annotations

import datetime
import types
from typing import Annotated, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)

from app.db.models import Base
from app.enums import (
    ActorType,
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
