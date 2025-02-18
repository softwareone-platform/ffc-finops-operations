import datetime

from app.schemas.accounts import AccountReference
from app.schemas.core import CommonEventsSchema, IdSchema


class ChargesFileRead(IdSchema, CommonEventsSchema):
    document_date: datetime.datetime
    amount: float | None
    currency: str
    owner: AccountReference
