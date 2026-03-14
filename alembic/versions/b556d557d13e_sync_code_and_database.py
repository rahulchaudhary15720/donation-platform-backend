"""sync code and database

Revision ID: b556d557d13e
Revises: 5b7162b5d1bd
Create Date: 2026-02-22 22:20:08.498263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b556d557d13e'
down_revision: Union[str, Sequence[str], None] = '5b7162b5d1bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
