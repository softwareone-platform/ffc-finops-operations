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


@enum.unique
class DataSourceType(str, enum.Enum):
    AWS_ROOT = "aws_root"
    AWS_LINKED = "aws_linked"
    AZURE_TENANT = "azure_tenant"
    AZURE_SUBSCRIPTION = "azure_subscription"
    GCP = "gcp"
