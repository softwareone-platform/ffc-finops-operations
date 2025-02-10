from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.human_readable_pk import HumanReadablePKMixin
from app.db.models import Base


class ModelForTests(Base, HumanReadablePKMixin):
    __tablename__ = "test_models"

    PK_PREFIX = "TMDL"
    PK_NUM_LENGTH = 4

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(255), nullable=False, default="active")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("related_models.id"), nullable=True)
    parent: Mapped["ParentModelForTests"] = relationship(foreign_keys=[parent_id])


class ParentModelForTests(Base, HumanReadablePKMixin):
    __tablename__ = "related_models"

    PK_PREFIX = "RMDL"
    PK_NUM_LENGTH = 4
    description: Mapped[str] = mapped_column(String(255), nullable=False)
