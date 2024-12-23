"""merge  7f131c1faf6c 90830ea1c796

Revision ID: 8a5758ec8e50
Revises: 7f131c1faf6c, 90830ea1c796
Create Date: 2024-12-23 17:47:21.538097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8a5758ec8e50'
down_revision: Union[str, None] = ('7f131c1faf6c', '90830ea1c796')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
