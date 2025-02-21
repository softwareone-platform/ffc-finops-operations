import datetime
import uuid
from typing import Annotated

from pydantic import Field

from app.schemas.core import BaseSchema


class EmployeeBase(BaseSchema):
    email: Annotated[str, Field(max_length=255, examples=["harry.potter@gryffindor.edu"])]
    display_name: Annotated[str, Field(max_length=255, examples=["Harry James Potter"])]
    # TODO: Common audit events too?
    created_at: datetime.datetime | None = None
    last_login: datetime.datetime | None = None
    roles_count: int | None = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeRead(EmployeeBase):
    id: uuid.UUID
