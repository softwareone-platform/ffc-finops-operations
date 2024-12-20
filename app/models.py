import datetime
import uuid

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class UUIDModel(SQLModel):
    id: uuid.UUID = Field(
        primary_key=True,
        nullable=False,
        default_factory=uuid.uuid4,
        index=True,
        sa_column_kwargs={
            "server_default": sa.text("gen_random_uuid()"),
            "unique": True,
        },
    )


class TimestampModel(SQLModel):
    created_at: datetime.datetime = Field(
        nullable=False,
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.text("current_timestamp(0)")},
    )

    updated_at: datetime.datetime = Field(
        nullable=False,
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": sa.text("current_timestamp(0)"),
            "onupdate": sa.text("current_timestamp(0)"),
        },
    )


class SoftDeletedModel(SQLModel):
    soft_deleted: bool = Field(
        nullable=False,
        index=True,
        sa_column_kwargs={"server_default": sa.sql.false()},
    )


class EntitlementBase(SQLModel):
    sponsor_name: str = Field(max_length=255, nullable=False)
    sponsor_external_id: str = Field(max_length=255, nullable=False)
    sponsor_container_id: str = Field(max_length=255, nullable=False)


class Entitlement(EntitlementBase, TimestampModel, UUIDModel, table=True):
    __tablename__ = "entitlements"

    activated_at: datetime.datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=sa.DateTime(timezone=True),
    )


class EntitlementRead(EntitlementBase, UUIDModel):
    activated_at: datetime.datetime | None


class EntitlementCreate(EntitlementBase):
    pass


class EntitlementUpdate(EntitlementBase):
    sponsor_name: str | None = None
    sponsor_external_id: str | None = None
    sponsor_container_id: str | None = None
