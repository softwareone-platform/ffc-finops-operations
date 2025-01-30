import random

from sqlalchemy import event, exists, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper


def generate_human_readable_pk(prefix: str, num_length: int, group_size: int = 4) -> str:
    """
    Generate a primary key with a given prefix, numeric length, and grouping size.

    :param prefix: The prefix string (uppercase letters).
    :param num_length: The total length of the numeric part.
    :param group_size: The size of each group in the numeric part (default: 4).
    :return: A formatted primary key string.
    """

    random_number = f"{random.randint(10**(num_length-1), 10**num_length - 1)}"  # nosec: B311
    grouped_number = "-".join(
        random_number[i : i + group_size] for i in range(0, len(random_number), group_size)
    )

    return f"{prefix}-{grouped_number}"


class HumanReadablePKMixin:
    """
    Mixin class for models requiring a human readable primary key generator.
    """

    PK_MAX_RETRIES = 15  # Maximum number of retries to avoid collisions
    PK_PREFIX = "DEF"  # Default prefix (override in subclasses)
    PK_NUM_LENGTH = 12  # Default numeric length (override in subclasses)
    PK_GROUP_SIZE = 4  # Default group size (override in subclasses)


@event.listens_for(HumanReadablePKMixin, "before_insert", propagate=True)
def on_before_insert(mapper: Mapper, connection: Connection, obj: HumanReadablePKMixin) -> None:
    from app.db.models import Base

    if not isinstance(obj, Base):  # pragma: no cover
        return

    if obj.id is not None:  # pragma: no cover
        return

    model_cls = obj.__class__

    for _ in range(model_cls.PK_MAX_RETRIES):
        pk = generate_human_readable_pk(
            prefix=model_cls.PK_PREFIX,
            num_length=model_cls.PK_NUM_LENGTH,
            group_size=model_cls.PK_GROUP_SIZE,
        )
        # Check for collision
        stmt = select(exists().where(model_cls.id == pk))
        result = connection.scalar(stmt)
        if not result:  # No collision found
            obj.id = pk
            return

    raise ValueError(
        f"Unable to generate unique primary key after {model_cls.PK_MAX_RETRIES} attempts."
    )


def build_id_regex(model: HumanReadablePKMixin) -> str:
    prefix_part = f"^{model.PK_PREFIX}"
    groups_count = (model.PK_NUM_LENGTH + model.PK_GROUP_SIZE - 1) // model.PK_GROUP_SIZE
    group_part = (r"-\d{" + str(model.PK_GROUP_SIZE) + r"}") * groups_count

    return f"{prefix_part}{group_part}$"
