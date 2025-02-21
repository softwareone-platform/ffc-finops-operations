import datetime
import uuid
from typing import Annotated

from pydantic import EmailStr, Field

from app.enums import AccountUserStatus, UserStatus
from app.schemas.accounts import AccountReference
from app.schemas.core import BaseSchema, CommonEventsSchema, IdSchema, PasswordInputSchema


class UserBase(BaseSchema):
    name: Annotated[str, Field(max_length=255, examples=["Lady Gaga"])]


class UserCreate(UserBase):
    email: Annotated[EmailStr, Field(max_length=255, examples=["lady.gaga@bennett.tony"])]


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
    user: UserReference
    invitation_token: str
    invitation_token_expires_at: datetime.datetime
    joined_at: datetime.datetime | None = None


class UserInvitationRead(IdSchema, CommonEventsSchema, UserCreate):
    account_user: AccountUserRead | None = None
    status: UserStatus
