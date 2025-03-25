"""Create unique constraint on datasource_expenses

Revision ID: 3679d9919a68
Revises: 2f61b7c85887
Create Date: 2025-03-20 21:51:11.390032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = '3679d9919a68'
down_revision: Union[str, None] = '2f61b7c85887'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint('uq_datasource_expenses_per_month', 'datasource_expenses', ['datasource_id', 'organization_id', 'year', 'month'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('uq_datasource_expenses_per_month', 'datasource_expenses', type_='unique')
    # ### end Alembic commands ###
