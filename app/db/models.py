import datetime

import sqlalchemy as sa
from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, relationship
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import FernetEngine

from app import settings
from app.db.human_readable_pk import HumanReadablePKMixin
from app.enums import ActorType, EntitlementStatus


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
        "polymorphic_identity": ActorType.USER,
        "polymorphic_on": "type",
    }


class AuditableMixin(TimestampMixin):
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), name="created_by")
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), name="updated_by")

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


class System(Actor, AuditableMixin):
    __tablename__ = "systems"

    PK_PREFIX = "FTKN"
    PK_NUM_LENGTH = 8

    id: Mapped[str] = mapped_column(ForeignKey("actors.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, unique=True)
    jwt_secret: Mapped[str] = mapped_column(
        StringEncryptedType(String(255), settings.secrets_encryption_key, FernetEngine),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String)

    __mapper_args__ = {
        "polymorphic_identity": ActorType.SYSTEM,
        "inherit_condition": id == Actor.id,
    }


class Entitlement(Base, HumanReadablePKMixin, AuditableMixin):
    __tablename__ = "entitlements"

    PK_PREFIX = "FENT"
    PK_NUM_LENGTH = 12

    sponsor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sponsor_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sponsor_container_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[EntitlementStatus] = mapped_column(
        Enum(EntitlementStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EntitlementStatus.NEW,
        server_default=EntitlementStatus.NEW.value,
    )
    activated_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    terminated_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    terminated_by_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    terminated_by: Mapped[Actor | None] = relationship(foreign_keys=[terminated_by_id])


class Organization(Base, AuditableMixin, HumanReadablePKMixin):
    __tablename__ = "organizations"

    PK_PREFIX = "FORG"
    PK_NUM_LENGTH = 12

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, unique=True)
    organization_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
