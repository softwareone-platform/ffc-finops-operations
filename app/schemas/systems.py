import secrets
from typing import Annotated

from pydantic import Field

from app.enums import SystemStatus
from app.schemas.accounts import AccountReference
from app.schemas.core import BaseSchema, CommonEventsSchema, IdSchema


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
    # NOTE: The type annotation of `name` is intentionally `str` and not `str | None`
    # despite the default value being `None`. This allows partial updatesof fields
    # other than `name`, however explicitly setting name to `None` fails the validation check.
    # Also, fields such as `description` are nullable, so we want to differentiate
    # between an explicit `None` and an unset value.

    name: str = None  # type: ignore[assignment]
    external_id: Annotated[str | None, Field(max_length=255)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    jwt_secret: Annotated[str | None, Field(min_length=64)] = None


class SystemCreateResponse(SystemRead):
    jwt_secret: str
