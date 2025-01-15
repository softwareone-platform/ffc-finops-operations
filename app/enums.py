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
class CloudAccountType(str, enum.Enum):
    AWS_CNR = "aws_cnr"
    AZURE_CNR = "azure_cnr"
    AZURE_TENANT = "azure_tenant"
    GCP_CNR = "gcp_cnr"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN
