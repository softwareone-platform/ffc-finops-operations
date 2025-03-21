"""move name from system and user to actor

Revision ID: 196f292f2ea2
Revises: 660df34b13b5
Create Date: 2025-03-12 18:57:46.664578

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = '196f292f2ea2'
down_revision: Union[str, None] = '660df34b13b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('actors', sa.Column('name', sa.String(length=255), nullable=True))
    op.execute("UPDATE actors SET name = systems.name FROM systems WHERE actors.id = systems.id")
    op.execute("UPDATE actors SET name = users.name FROM users WHERE actors.id = users.id")
    op.drop_column('systems', 'name')
    op.drop_column('users', 'name')
    op.alter_column('actors', 'name', nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('systems', sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.execute("UPDATE systems SET name = actors.name FROM actors WHERE systems.id = actors.id")
    op.execute("UPDATE users SET name = actors.name FROM actors WHERE users.id = actors.id")
    op.alter_column('users', 'name', nullable=False)
    op.alter_column('systems', 'name', nullable=False)
    op.drop_column('actors', 'name')
    # ### end Alembic commands ###
