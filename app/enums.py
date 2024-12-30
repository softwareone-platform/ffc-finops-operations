import enum


@enum.unique
class ActorType(str, enum.Enum):
    USER = "user"
    SYSTEM = "system"


@enum.unique
class EntitlementStatus(str, enum.Enum):
    NEW = "new"
    ACTIVE = "active"
    TERMINATED = "terminated"
