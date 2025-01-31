from typing import Annotated

from fastapi import Depends, Path

from app.db import DBSession
from app.db.handlers import EntitlementHandler, OrganizationHandler
from app.db.models import Entitlement, Organization


def get_entitlement_handler(session: DBSession) -> EntitlementHandler:
    return EntitlementHandler(session)


def get_organization_handler(session: DBSession) -> OrganizationHandler:
    return OrganizationHandler(session)


EntitlementRepository = Annotated[EntitlementHandler, Depends(get_entitlement_handler)]
OrganizationRepository = Annotated[OrganizationHandler, Depends(get_organization_handler)]

EntitlementId = Annotated[str, Path(pattern=Entitlement.build_id_regex())]
OrganizationId = Annotated[str, Path(pattern=Organization.build_id_regex())]
