"""Add termination fields to entitlement

Revision ID: 36f24766198d
Revises: 7aed980f816e
Create Date: 2025-01-08 16:32:40.172463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = '36f24766198d'
down_revision: Union[str, None] = '7aed980f816e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('entitlements', sa.Column('terminated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('entitlements', sa.Column('terminated_by_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(None, 'entitlements', 'actors', ['terminated_by_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'entitlements', type_='foreignkey')
    op.drop_column('entitlements', 'terminated_by_id')
    op.drop_column('entitlements', 'terminated_at')
    # ### end Alembic commands ###
