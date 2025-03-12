from typing import Annotated

from pydantic import Field

from app.enums import AccountStatus, AccountType
from app.schemas.core import BaseSchema, CommonEventsSchema, IdSchema


class AccountEntitlementsStats(BaseSchema):
    new: Annotated[int, Field(examples=["5"], default=0)]
    redeemed: Annotated[int, Field(examples=["4"], default=0)]
    terminated: Annotated[int, Field(examples=["12"], default=0)]


class AccountBase(BaseSchema):
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
            examples=["Microsoft"],
            description="The name of the account",
        ),
    ]
    external_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
            examples=["ACC-9044-8753"],
            description="An external identifier for the account",
        ),
    ]


class AccountCreate(AccountBase):
    type: AccountType


class AccountUpdate(BaseSchema):
    name: Annotated[str | None, Field(min_length=1, max_length=255, examples=["Microsoft"])] = None
    external_id: Annotated[
        str | None, Field(min_length=1, max_length=255, examples=["ACC-9044-8753"])
    ] = None


class AccountReference(IdSchema):
    name: Annotated[str, Field(max_length=255, examples=["Microsoft"])]
    type: AccountType


# Importing here to avoid circular imports
from app.schemas.users import AccountUserReferenceWithUser  # noqa: E402


class AccountRead(IdSchema, CommonEventsSchema, AccountBase):
    entitlements_stats: AccountEntitlementsStats | None = None
    account_user: AccountUserReferenceWithUser | None
    status: AccountStatus
    type: AccountType
