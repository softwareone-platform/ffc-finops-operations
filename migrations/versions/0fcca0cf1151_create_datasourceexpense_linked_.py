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
    # Add the new column with nullable=True as there are existing rows
    op.add_column('datasource_expenses', sa.Column('linked_datasource_id', sa.String(length=255), nullable=True))
    
    # Set the default value for existing rows to an empty string
    op.execute(sa.text("UPDATE datasource_expenses SET linked_datasource_id = ''"))
    
    # Remove the nullable constraint now that all existing rows have a value
    op.alter_column( 'datasource_expenses', 'linked_datasource_id', existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    op.drop_column('datasource_expenses', 'linked_datasource_id')
