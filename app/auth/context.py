from contextvars import ContextVar
from dataclasses import dataclass

from app.db.models import Account, Actor, System, User
from app.enums import ActorType


@dataclass
class AuthenticationContext:
    account: Account
    actor_type: ActorType
    system: System | None = None
    user: User | None = None

    def get_actor(self) -> Actor | None:
        if self.actor_type == ActorType.SYSTEM:
            return self.system
        return self.user


auth_context = ContextVar[AuthenticationContext]("auth_context")
