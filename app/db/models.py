import datetime
from contextlib import suppress

import sqlalchemy as sa
from sqlalchemy import Connection, Enum, ForeignKey, Index, String, Text, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Mapper,
    declared_attr,
    mapped_column,
    relationship,
)
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import FernetEngine

from app.conf import get_settings
from app.db.human_readable_pk import HumanReadablePKMixin
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


def get_current_actor_id() -> str | None:
    from app.auth.context import auth_context

    with suppress(LookupError):
        actor = auth_context.get().get_actor()

        if actor is not None:
            return actor.id


class AuditableMixin(TimestampMixin):
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("actors.id"),
        name="created_by",
        default=get_current_actor_id,
    )
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("actors.id"),
        name="updated_by",
        default=get_current_actor_id,
        onupdate=get_current_actor_id,
    )
    deleted_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("actors.id"),
        name="deleted_by",
    )

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

    @classmethod
    def __declare_last__(cls):
        event.listen(cls, "before_update", cls._receive_before_update)

    @staticmethod
    def _receive_before_update(
        mapper: Mapper,
        connection: Connection,
        target: "AuditableMixin",
    ) -> None:
        # ref: https://stackoverflow.com/a/69645377
        insp = sa.inspect(target, raiseerr=True)

        # TODO: Add the same for TimestampMixin
        # TODO: If deleted_at and deleted_by are explicitly set, do not override them
        # TODO: Add the same for terminated_by and terminated_at, and redeemed_at and redeemed_by
        #       Maybe just call call a method like "on_status_change"?
        # We can also generalise the fuck out of this :)  (esp. with more introspection) but
        # that'd be an overkill

        try:
            status_history = insp.attrs.status.history
        except AttributeError:
            # no status column
            return

        if not status_history.has_changes():
            return

        old_status, new_status = status_history.deleted[0], status_history.added[0]

        if old_status == "deleted" and new_status != "deleted":
            target.deleted_at = None
            target.deleted_by_id = None
        elif old_status != "deleted" and new_status == "deleted":
            target.deleted_at = datetime.datetime.now(datetime.UTC)
            target.deleted_by_id = get_current_actor_id()


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
