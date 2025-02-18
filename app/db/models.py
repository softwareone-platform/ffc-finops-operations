import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, relationship
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import FernetEngine

from app.conf import get_settings
from app.db.human_readable_pk import HumanReadablePKMixin
from app.enums import (
    AccountStatus,
    AccountType,
    AccountUserStatus,
    ActorType,
    ChargesFileStatus,
    DatasourceType,
    EntitlementStatus,
    OrganizationStatus,
    SystemStatus,
    UserStatus,
)


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(
        primary_key=True,
        unique=True,
        index=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        server_default=sa.func.current_timestamp(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class Actor(Base, HumanReadablePKMixin):
    __tablename__ = "actors"

    type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ActorType.USER,
        server_default=ActorType.USER.value,
        index=True,
    )

    __mapper_args__ = {
        "polymorphic_on": "type",
    }


class AuditableMixin(TimestampMixin):
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), name="created_by")
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), name="updated_by")
    deleted_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), name="deleted_by")

    @declared_attr
    def created_by(cls) -> Mapped["Actor"]:
        return relationship(
            "Actor",
            foreign_keys=lambda: [cls.__dict__["created_by_id"]],
            lazy="joined",
        )

    @declared_attr
    def updated_by(cls) -> Mapped["Actor"]:
        return relationship(
            "Actor",
            foreign_keys=lambda: [cls.__dict__["updated_by_id"]],
            lazy="joined",
        )

    @declared_attr
    def deleted_by(cls) -> Mapped["Actor"]:
        return relationship(
            "Actor",
            foreign_keys=lambda: [cls.__dict__["deleted_by_id"]],
            lazy="joined",
        )


class Account(Base, HumanReadablePKMixin, AuditableMixin):
    __tablename__ = "accounts"

    PK_PREFIX = "FACC"
    PK_NUM_LENGTH = 8

    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AccountType.AFFILIATE,
        server_default=AccountType.AFFILIATE.value,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AccountStatus.ACTIVE,
        server_default=AccountStatus.ACTIVE.value,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    users: Mapped[list["AccountUser"]] = relationship(back_populates="account")


class System(Actor, AuditableMixin):
    __tablename__ = "systems"

    PK_PREFIX = "FTKN"
    PK_NUM_LENGTH = 8

    id: Mapped[str] = mapped_column(ForeignKey("actors.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    jwt_secret: Mapped[str] = mapped_column(
        StringEncryptedType(
            String(255), lambda: get_settings().secrets_encryption_key, FernetEngine
        ),
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    owner: Mapped[Account] = relationship(foreign_keys=[owner_id])
    status: Mapped[SystemStatus] = mapped_column(
        Enum(SystemStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SystemStatus.ACTIVE,
        server_default=SystemStatus.ACTIVE.value,
    )

    __mapper_args__ = {
        "polymorphic_identity": ActorType.SYSTEM.value,
        "inherit_condition": id == Actor.id,
        "polymorphic_load": "inline",
    }

    __table_args__ = (
        Index(
            "ix_systems_external_id_for_non_deleted",
            external_id,
            unique=True,
            postgresql_where=(status != SystemStatus.DELETED),
        ),
    )


class User(Actor, HumanReadablePKMixin, AuditableMixin):
    __tablename__ = "users"

    PK_PREFIX = "FUSR"
    PK_NUM_LENGTH = 8

    id: Mapped[str] = mapped_column(ForeignKey("actors.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_used_account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    last_used_account: Mapped[Account | None] = relationship(foreign_keys=[last_used_account_id])
    pwd_reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pwd_reset_token_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=UserStatus.DRAFT,
        server_default=UserStatus.DRAFT.value,
    )
    accounts: Mapped[list["AccountUser"]] = relationship(back_populates="user")

    @property
    def account_user(self):
        try:
            return self.accounts[0]
        except Exception:
            # todo : improve this excepption
            return None

    __mapper_args__ = {
        "polymorphic_identity": ActorType.USER.value,
        "inherit_condition": id == Actor.id,
        "polymorphic_load": "inline",
    }


class AccountUser(Base, AuditableMixin, HumanReadablePKMixin):
    __tablename__ = "accounts_users"

    PK_PREFIX = "FAUR"
    PK_NUM_LENGTH = 12

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    account: Mapped["Account"] = relationship(back_populates="users", foreign_keys=[account_id])
    user: Mapped["User"] = relationship(back_populates="accounts", foreign_keys=[user_id])
    invitation_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invitation_token_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    joined_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[AccountUserStatus] = mapped_column(
        Enum(AccountUserStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AccountUserStatus.INVITED,
        server_default=AccountUserStatus.INVITED.value,
    )


class Organization(Base, AuditableMixin, HumanReadablePKMixin):
    __tablename__ = "organizations"

    PK_PREFIX = "FORG"
    PK_NUM_LENGTH = 12

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    operations_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    linked_organization_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(OrganizationStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )

    __table_args__ = (
        Index(
            "ix_organizations_operations_external_id_for_non_deleted",
            operations_external_id,
            unique=True,
            postgresql_where=(status != OrganizationStatus.DELETED),
        ),
    )


class Entitlement(Base, HumanReadablePKMixin, AuditableMixin):
    __tablename__ = "entitlements"

    PK_PREFIX = "FENT"
    PK_NUM_LENGTH = 12

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    affiliate_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    datasource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    linked_datasource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_datasource_type: Mapped[DatasourceType | None] = mapped_column(
        Enum(DatasourceType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    linked_datasource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    owner: Mapped[Account] = relationship(foreign_keys=[owner_id])
    status: Mapped[EntitlementStatus] = mapped_column(
        Enum(EntitlementStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EntitlementStatus.NEW,
        server_default=EntitlementStatus.NEW.value,
    )
    redeemed_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    redeemed_by_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"))
    redeemed_by: Mapped[Organization | None] = relationship(foreign_keys=[redeemed_by_id])

    terminated_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    terminated_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    terminated_by: Mapped[Actor | None] = relationship(foreign_keys=[terminated_by_id])


class ChargesFile(Base, HumanReadablePKMixin, TimestampMixin):
    __tablename__ = "invoices"

    PK_PREFIX = "FCHG"
    PK_NUM_LENGTH = 12

    document_date: Mapped[datetime.date] = mapped_column(sa.Date())
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    owner: Mapped[Account] = relationship(foreign_keys=[owner_id])
    status: Mapped[ChargesFileStatus] = mapped_column(
        Enum(ChargesFileStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ChargesFileStatus.DRAFT,
        server_default=ChargesFileStatus.DRAFT.value,
    )
