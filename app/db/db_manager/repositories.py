from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import ColumnExpressionArgument, select
from sqlalchemy.orm import joinedload

from app.auth.context import auth_context
from app.db import DBSession
from app.db.db_manager.model_handler import ModelHandler
from app.db.models import (
    Account,
    AccountUser,
    Entitlement,
    Organization,
    System,
    User,
)
from app.enums import EntitlementStatus


class RepositoryFactory:
    def __init__(self, handler_cls: type[ModelHandler]):
        self.handler_class = handler_cls

    def __call__(self, session: DBSession) -> ModelHandler:
        return self.handler_class(session)


class EntitlementHandler(ModelHandler[Entitlement]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(Entitlement.owner),
            joinedload(Entitlement.created_by),
            joinedload(Entitlement.updated_by),
        ]

    async def terminate(self, entitlement: Entitlement) -> Entitlement:
        return await self.update(
            entitlement.id,
            {
                "status": EntitlementStatus.TERMINATED,
                "terminated_at": datetime.now(UTC),
                "terminated_by": auth_context.get().get_actor(),
            },
        )


class OrganizationHandler(ModelHandler[Organization]):
    pass


class SystemHandler(ModelHandler[System]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [joinedload(System.owner)]


class AccountHandler(ModelHandler[Account]):
    pass


class UserHandler(ModelHandler[User]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(User.last_used_account),
        ]


class AccountUserHandler(ModelHandler[AccountUser]):
    def __init__(self, session):
        super().__init__(session)
        self.default_options = [
            joinedload(AccountUser.account),
            joinedload(AccountUser.user),
        ]

    async def get_account_user(
        self,
        account_id: str,
        user_id: str,
        extra_conditions: list[ColumnExpressionArgument] | None = None,
    ) -> AccountUser | None:
        query = select(self.model_cls).where(
            self.model_cls.account_id == account_id,
            self.model_cls.user_id == user_id,
        )
        if extra_conditions:
            query = query.where(*extra_conditions)
        if self.default_options:
            query = query.options(*self.default_options)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


EntitlementRepository = Annotated[
    EntitlementHandler, Depends(RepositoryFactory(EntitlementHandler))
]
OrganizationRepository = Annotated[
    OrganizationHandler, Depends(RepositoryFactory(OrganizationHandler))
]
AccountRepository = Annotated[AccountHandler, Depends(RepositoryFactory(AccountHandler))]
UserRepository = Annotated[UserHandler, Depends(RepositoryFactory(UserHandler))]
AccountUserRepository = Annotated[
    AccountUserHandler, Depends(RepositoryFactory(AccountUserHandler))
]
SystemRepository = Annotated[SystemHandler, Depends(RepositoryFactory(SystemHandler))]
