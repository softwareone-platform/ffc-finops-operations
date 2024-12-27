"""Added organization_id

Revision ID: 7915164f66be
Revises: 8a5758ec8e50
Create Date: 2024-12-27 10:27:37.156714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7915164f66be'
down_revision: Union[str, None] = '8a5758ec8e50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('organizations', sa.Column('organization_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True))
    op.create_index(op.f('ix_organizations_organization_id'), 'organizations', ['organization_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_organizations_organization_id'), table_name='organizations')
    op.drop_column('organizations', 'organization_id')
    # ### end Alembic commands ###