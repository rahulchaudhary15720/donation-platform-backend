"""restore password_reset_tokens table

Revision ID: c9f1e7a2d4b0
Revises: a1b2c3d4e5f6
Create Date: 2026-03-15 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9f1e7a2d4b0"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "password_reset_tokens"
INDEX_NAME = "ix_password_reset_tokens_token_hash"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE_NAME):
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes(TABLE_NAME)} if inspector.has_table(TABLE_NAME) else set()
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, TABLE_NAME, ["token_hash"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(TABLE_NAME):
        indexes = {idx["name"] for idx in inspector.get_indexes(TABLE_NAME)}
        if INDEX_NAME in indexes:
            op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
        op.drop_table(TABLE_NAME)
