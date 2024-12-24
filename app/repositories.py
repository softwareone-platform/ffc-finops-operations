from typing import Annotated

from fastapi import Depends

from app.db import DBSession
from app.db.handlers import EntitlementHandler, OrganizationHandler, SystemHandler


def get_entitlement_handler(session: DBSession) -> EntitlementHandler:
    return EntitlementHandler(session)


def get_organization_handler(session: DBSession) -> OrganizationHandler:
    return OrganizationHandler(session)


def get_system_handler(session: DBSession) -> SystemHandler:
    return SystemHandler(session)


EntitlementRepository = Annotated[EntitlementHandler, Depends(get_entitlement_handler)]
OrganizationRepository = Annotated[OrganizationHandler, Depends(get_organization_handler)]
SystemRepository = Annotated[SystemHandler, Depends(get_system_handler)]
