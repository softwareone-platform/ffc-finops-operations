from typing import Annotated

from fastapi import Depends, Path

from app.auth.auth import get_authentication_context
from app.auth.context import AuthenticationContext
from app.db import DBSession, handlers, models

#######
# Repositories
#######


class HandlerFactory:
    def __init__(self, handler_cls: type[handlers.ModelHandler]):
        self.handler_class = handler_cls

    def __call__(self, session: DBSession) -> handlers.ModelHandler:
        return self.handler_class(session)


EntitlementRepository = Annotated[
    handlers.EntitlementHandler, Depends(HandlerFactory(handlers.EntitlementHandler))
]
OrganizationRepository = Annotated[
    handlers.OrganizationHandler, Depends(HandlerFactory(handlers.OrganizationHandler))
]
AccountRepository = Annotated[
    handlers.AccountHandler, Depends(HandlerFactory(handlers.AccountHandler))
]
UserRepository = Annotated[handlers.UserHandler, Depends(HandlerFactory(handlers.UserHandler))]
AccountUserRepository = Annotated[
    handlers.AccountUserHandler, Depends(HandlerFactory(handlers.AccountUserHandler))
]
SystemRepository = Annotated[
    handlers.SystemHandler, Depends(HandlerFactory(handlers.SystemHandler))
]

#######
# Ids path parameters
#######

EntitlementId = Annotated[str, Path(pattern=models.Entitlement.build_id_regex())]
OrganizationId = Annotated[str, Path(pattern=models.Organization.build_id_regex())]
SystemId = Annotated[str, Path(pattern=models.System.build_id_regex())]
AccountId = Annotated[str, Path(pattern=models.Account.build_id_regex())]
UserId = Annotated[str, Path(pattern=models.User.build_id_regex())]


#######
# Auth context
#######

CurrentAuthContext = Annotated[AuthenticationContext, Depends(get_authentication_context)]
