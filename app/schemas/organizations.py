import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.enums import DatasourceType, OrganizationStatus
from app.schemas.core import BaseSchema, CommonEventsSchema, IdSchema


class OrganizationExpensesInfo(BaseSchema):
    limit: Annotated[Decimal, Field(max_length=255, examples=["10,000.00"], default=Decimal(0))]
    expenses_last_month: Annotated[
        Decimal, Field(max_length=255, examples=["4,321.26"], default=Decimal(0))
    ]
    expenses_this_month: Annotated[
        Decimal, Field(max_length=255, examples=["2,111.49"], default=Decimal(0))
    ]
    expenses_this_month_forecast: Annotated[
        Decimal, Field(max_length=255, examples=["5,001.12"], default=Decimal(0))
    ]
    possible_monthly_saving: Annotated[
        Decimal, Field(max_length=255, examples=["4.66"], default=Decimal(0))
    ]


class OrganizationBase(BaseSchema):
    name: Annotated[str, Field(min_length=1, max_length=255, examples=["Nimbus Nexus Inc."])]
    currency: Annotated[str, Field(examples=["EUR"])]
    operations_external_id: Annotated[
        str, Field(min_length=1, max_length=255, examples=["AGR-9876-5534-9172"])
    ]


class OrganizationCreate(OrganizationBase):
    user_id: str


class OrganizationRead(IdSchema, CommonEventsSchema, OrganizationBase):
    linked_organization_id: Annotated[
        str | None, Field(max_length=255, examples=["ee7ebfaf-a222-4209-aecc-67861694a488"])
    ] = None
    status: OrganizationStatus
    expenses_info: OrganizationExpensesInfo | None = None


class OrganizationUpdate(BaseSchema):
    name: Annotated[
        str | None, Field(min_length=1, max_length=255, examples=["Nimbus Nexus Inc."])
    ] = None
    operations_external_id: Annotated[
        str | None, Field(min_length=1, max_length=255, examples=["AGR-9876-5534-9172"])
    ] = None


class OrganizationReference(IdSchema, OrganizationBase):
    pass


class DatasourceRead(BaseSchema):
    id: uuid.UUID
    organization_id: str
    type: DatasourceType
    resources_changed_this_month: int
    expenses_so_far_this_month: float
    expenses_forecast_this_month: float
