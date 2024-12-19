from typing import Annotated

from fastapi import Depends

from app.db import DBSession
from app.db.handlers import EntitlementHandler, OrganizationHandler


def get_entitlement_handler(session: DBSession) -> EntitlementHandler:
    return EntitlementHandler(session)


def get_organization_handler(session: DBSession) -> OrganizationHandler:
    return OrganizationHandler(session)


EntitlementRepository = Annotated[EntitlementHandler, Depends(get_entitlement_handler)]
OrganizationRepository = Annotated[OrganizationHandler, Depends(get_organization_handler)]
