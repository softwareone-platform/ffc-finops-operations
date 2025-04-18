"""Create datasources_expenses table

Revision ID: 2f61b7c85887
Revises: 80ece7cdb363
Create Date: 2025-03-20 16:17:12.811064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = '2f61b7c85887'
down_revision: Union[str, None] = '80ece7cdb363'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('datasource_expenses',
    sa.Column('datasource_id', sa.String(length=255), nullable=False),
    sa.Column('organization_id', sa.String(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('month_expenses', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=True),
    sa.Column('updated_by', sa.String(), nullable=True),
    sa.Column('deleted_by', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['deleted_by'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['actors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_datasource_expenses_datasource_id'), 'datasource_expenses', ['datasource_id'], unique=False)
    op.create_index(op.f('ix_datasource_expenses_id'), 'datasource_expenses', ['id'], unique=True)
    op.create_index('ix_datasource_expenses_year_and_month', 'datasource_expenses', ['year', 'month'], unique=False)
    op.create_index(op.f('ix_entitlements_datasource_id'), 'entitlements', ['datasource_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_entitlements_datasource_id'), table_name='entitlements')
    op.drop_index('ix_datasource_expenses_year_and_month', table_name='datasource_expenses')
    op.drop_index(op.f('ix_datasource_expenses_id'), table_name='datasource_expenses')
    op.drop_index(op.f('ix_datasource_expenses_datasource_id'), table_name='datasource_expenses')
    op.drop_table('datasource_expenses')
    # ### end Alembic commands ###
