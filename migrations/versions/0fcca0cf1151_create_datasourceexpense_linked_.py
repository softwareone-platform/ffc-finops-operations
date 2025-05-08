"""Create DatasourceExpense.linked_datasource_id

Revision ID: 0fcca0cf1151
Revises: 7cd884694384
Create Date: 2025-05-07 12:30:00.321343

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = '0fcca0cf1151'
down_revision: Union[str, None] = '7cd884694384'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add a new column with "" as the default value (so that the migration can be run on a live database)
    op.add_column('datasource_expenses', sa.Column('linked_datasource_id', sa.String(length=255), server_default="", nullable=False))
    
    # Remove the server_default from the column, so that any *future* inserts will require a value to be provided
    op.alter_column( 'datasource_expenses', 'linked_datasource_id', server_default=None)


def downgrade() -> None:
    op.drop_column('datasource_expenses', 'linked_datasource_id')
