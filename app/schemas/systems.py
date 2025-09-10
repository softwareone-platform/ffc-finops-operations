import secrets
from typing import Annotated

from pydantic import Field

from app.enums import SystemStatus
from app.schemas.accounts import AccountReference
from app.schemas.core import BaseSchema, CommonEventsSchema, IdSchema


class SystemBase(BaseSchema):
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
            examples=["IBM Extension"],
        ),
    ]
    external_id: Annotated[str, Field(min_length=1, max_length=255, examples=["IBM_EXTENSION"])]
    description: Annotated[str | None, Field(max_length=2000, examples=["IBM Cloud Extension"])] = (
        None
    )
    owner: AccountReference


class SystemRead(IdSchema, CommonEventsSchema, SystemBase):
    status: SystemStatus


class SystemCreate(SystemBase):
    owner: Annotated[IdSchema | None, Field(examples=["FACC-5810-4583"])] = None  # type: ignore[assignment]
    jwt_secret: Annotated[
        str | None,
        Field(
            min_length=64,
            default_factory=lambda: secrets.token_hex(64),
            examples=[
                "3e3068bfcacd587f75137afdead8f96adb016734a68630cac9e7a008458782a38ef61217d17406832f8fede61a7773866430f52084f8cac59311386e1b673261"
            ],
        ),
    ] = None


class SystemUpdate(BaseSchema):
    # NOTE: The type annotation of `name` is intentionally `str` and not `str | None`
    # despite the default value being `None`. This allows partial updatesof fields
    # other than `name`, however explicitly setting name to `None` fails the validation check.
    # Also, fields such as `description` are nullable, so we want to differentiate
    # between an explicit `None` and an unset value.

    name: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
            examples=["ibm extension"],
        ),
    ] = None
    external_id: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    jwt_secret: Annotated[str | None, Field(min_length=64)] = None


class SystemCreateResponse(SystemRead):
    jwt_secret: str
