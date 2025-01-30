from typing import Annotated

from fastapi import Depends, Path

from app.db import DBSession
from app.db.handlers import EntitlementHandler, OrganizationHandler
from app.db.human_readable_pk import build_id_regex
from app.db.models import Entitlement, Organization


def get_entitlement_handler(session: DBSession) -> EntitlementHandler:
    return EntitlementHandler(session)


def get_organization_handler(session: DBSession) -> OrganizationHandler:
    return OrganizationHandler(session)


EntitlementRepository = Annotated[EntitlementHandler, Depends(get_entitlement_handler)]
OrganizationRepository = Annotated[OrganizationHandler, Depends(get_organization_handler)]

EntitlementId = Annotated[str, Path(pattern=build_id_regex(Entitlement))]
OrganizationId = Annotated[str, Path(pattern=build_id_regex(Organization))]
