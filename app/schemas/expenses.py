from decimal import Decimal

from app.enums import DatasourceType
from app.schemas.core import CommonEventsSchema, IdSchema
from app.schemas.entitlements import EntitlementRead
from app.schemas.organizations import OrganizationReference


class DatasourceExpenseRead(IdSchema, CommonEventsSchema):
    linked_datasource_id: str
    datasource_name: str
    linked_datasource_type: DatasourceType
    organization: OrganizationReference
    year: int
    month: int
    month_expenses: Decimal
    entitlements: list[EntitlementRead]
